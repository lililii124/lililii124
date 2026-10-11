"""Refresh the public upstream PR table in a GitHub profile README."""

import argparse
from datetime import datetime, timedelta, timezone
import html
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import quote, urlparse


START = '<!-- OPEN-SOURCE-WORK:START -->'
END = '<!-- OPEN-SOURCE-WORK:END -->'
PROJECT_NAMES = {
    'deepmodeling/jax-fem': 'JAX-FEM',
    'sofa-framework/sofa': 'SOFA',
    'pypr/pysph': 'PySPH',
    'peridigm/peridigm': 'Peridigm',
}


def fetch_pull_requests(login, gh='gh'):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', login):
        raise ValueError('Invalid GitHub login')
    query = f'is:pr is:public author:{login} -user:{login}'
    items = {}
    expected = None
    for page in range(1, 11):
        result = subprocess.run(
            [gh, 'api', '--method', 'GET', 'search/issues',
             '-H', 'Accept: application/vnd.github+json',
             '-H', 'X-GitHub-Api-Version: 2022-11-28',
             '-f', f'q={query}', '-f', 'sort=created', '-f', 'order=asc',
             '-f', 'per_page=100', '-f', f'page={page}'],
            check=True, capture_output=True, text=True, encoding='utf-8', timeout=60)
        data = json.loads(result.stdout)
        if data.get('incomplete_results') is not False:
            raise RuntimeError('GitHub returned incomplete search results; README left unchanged')
        count = data['total_count']
        if count > 1000:
            raise RuntimeError('Search exceeds 1,000 PRs; split the query before updating')
        if expected is None:
            expected = count
        elif count != expected:
            raise RuntimeError('PR count changed during pagination; retry the update')
        batch = data['items']
        for item in batch:
            if item['html_url'] in items:
                raise RuntimeError('Duplicate PR across search pages; retry the update')
            items[item['html_url']] = item
        if len(items) == expected:
            return list(items.values())
        if not batch or len(items) > expected:
            break
    raise RuntimeError('Missing search results; README left unchanged')


def markdown_text(value, limit=None):
    text = ' '.join(value.split())
    if limit and len(text) > limit:
        text = text[:limit - 1].rstrip() + '…'
    text = html.escape(text, quote=False)
    for character in '\\[]*_`':
        text = text.replace(character, '\\' + character)
    return text.replace('|', '&#124;')


def pr_search(repository, login, state):
    query = quote(f'is:pr author:{login} is:{state}', safe='')
    return f'https://github.com/{repository}/pulls?q={query}'


def render_table(items, login, checked_on):
    projects = {}
    for item in items:
        if item['user']['login'].casefold() != login.casefold():
            raise ValueError('Search returned a different author')
        repo_url = urlparse(item['repository_url'])
        parts = repo_url.path.strip('/').split('/')
        if repo_url.scheme != 'https' or repo_url.netloc != 'api.github.com' or len(parts) != 3 or parts[0] != 'repos':
            raise ValueError('Unexpected repository URL')
        owner, name = parts[1:]
        if owner.casefold() == login.casefold():
            continue
        repository = f'{owner}/{name}'
        expected_url = f'https://github.com/{repository}/pull/{item["number"]}'
        if item['html_url'] != expected_url:
            raise ValueError('Unexpected PR URL')
        pull_request = item['pull_request']
        if 'merged_at' not in pull_request:
            raise ValueError('Missing merge status; README left unchanged')
        merged = pull_request['merged_at'] is not None
        opened = item['state'] == 'open' and not merged
        if not merged and not opened:
            continue
        project = projects.setdefault(repository, {'merged': 0, 'open': 0, 'latest': item})
        project['merged'] += int(merged)
        project['open'] += int(opened)
        if (item['updated_at'], item['number']) > (project['latest']['updated_at'], project['latest']['number']):
            project['latest'] = item

    merged_total = sum(project['merged'] for project in projects.values())
    open_total = sum(project['open'] for project in projects.values())
    repository_label = 'repository' if len(projects) == 1 else 'repositories'
    lines = [f'**{merged_total} merged · {open_total} open · {len(projects)} {repository_label}**', '',
             '| Project | Merged PRs | Open PRs | Latest contribution |',
             '| --- | ---: | ---: | --- |']
    ordered = sorted(projects.items(), key=lambda pair: (
        pair[1]['merged'] > 0, pair[1]['latest']['updated_at'], pair[0]), reverse=True)
    for repository, project in ordered:
        name = PROJECT_NAMES.get(repository, repository.split('/')[1])
        counts = [f'[{project[state]}]({pr_search(repository, login, state)})'
                  if project[state] else '—' for state in ['merged', 'open']]
        latest = project['latest']
        title = markdown_text(latest['title'], limit=68)
        draft = ' (draft)' if latest.get('draft') else ''
        lines.append(f'| [{markdown_text(name)}](https://github.com/{repository}) | '
                     f'{counts[0]} | {counts[1]} | [#{latest["number"]} · {title}]({latest["html_url"]}){draft} |')
    if not projects:
        lines = ['No public upstream pull requests yet.']
    lines += ['', f'<sub>Public upstream pull requests · updated {checked_on} · refreshed twice daily</sub>']
    return '\n'.join(lines)


def replace_section(readme, section):
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError('Expected exactly one pair of Open-source work markers')
    start = readme.index(START) + len(START)
    end = readme.index(END)
    if start > end:
        raise ValueError('Open-source work markers are reversed')
    newline = '\r\n' if '\r\n' in readme else '\n'
    return readme[:start] + newline + section.replace('\n', newline) + newline + readme[end:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--login', required=True)
    parser.add_argument('--readme', type=Path, default=Path(__file__).resolve().parents[1] / 'README.md')
    parser.add_argument('--gh', default='gh')
    parser.add_argument('--check', action='store_true', help='Check without modifying README')
    args = parser.parse_args()
    original = args.readme.read_bytes().decode('utf-8')
    replace_section(original, '')  # Validate markers before accessing GitHub.
    items = fetch_pull_requests(args.login, args.gh)
    checked_on = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    updated = replace_section(original, render_table(items, args.login, checked_on))
    if updated == original:
        print('Open-source work is current.')
        return 0
    if args.check:
        print('Open-source work has new data.')
        return 1
    temporary = args.readme.with_name(args.readme.name + '.tmp')
    try:
        temporary.write_bytes(updated.encode('utf-8'))
        temporary.replace(args.readme)
    finally:
        temporary.unlink(missing_ok=True)
    print('Updated Open-source work.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
