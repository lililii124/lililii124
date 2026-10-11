import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import update_open_source as updater


def pull(number=1, repository='upstream/project', state='open', merged=False, title='Add a model'):
    return {
        'number': number,
        'user': {'login': 'example'},
        'repository_url': f'https://api.github.com/repos/{repository}',
        'html_url': f'https://github.com/{repository}/pull/{number}',
        'state': state,
        'pull_request': {'merged_at': '2026-01-01T00:00:00Z' if merged else None},
        'updated_at': '2026-01-02T00:00:00Z',
        'title': title,
        'draft': False,
    }


def response(items, total=None, incomplete=False):
    data = {'total_count': len(items) if total is None else total,
            'incomplete_results': incomplete, 'items': items}
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(data))


class UpdateTests(unittest.TestCase):
    def test_counts_exclude_unmerged_closed_and_own_repositories(self):
        items = [pull(1, state='closed', merged=True), pull(2), pull(3, state='closed'),
                 pull(4, repository='example/fork', state='closed', merged=True)]
        items[1]['draft'] = True
        text = updater.render_table(items, 'example', '2026-01-02')
        self.assertIn('1 merged · 1 open · 1 repository', text)
        self.assertIn('(draft)', text)
        self.assertNotIn('pull/3', text)
        self.assertNotIn('example/fork', text)

    def test_new_project_appears_without_configuration(self):
        text = updater.render_table([pull(repository='another/new-project')], 'example', '2026-01-02')
        self.assertIn('[new-project](https://github.com/another/new-project)', text)
        self.assertIn('0 merged · 1 open · 1 repository', text)

    def test_missing_merge_status_does_not_become_a_false_merged_count(self):
        item = pull(state='closed')
        del item['pull_request']['merged_at']
        with self.assertRaises(ValueError):
            updater.render_table([item], 'example', '2026-01-02')

    def test_title_cannot_break_table_or_inject_html(self):
        text = updater.render_table([pull(title='x | y\n[link](bad) <img src=x>')], 'example', '2026-01-02')
        row = next(line for line in text.splitlines() if '/pull/1)' in line)
        self.assertEqual(row.count('|'), 5)
        self.assertIn('&#124;', row)
        self.assertIn('&lt;img src=x&gt;', row)
        self.assertIn('\\[link\\]', row)

    def test_foreign_url_rejected(self):
        item = pull()
        item['html_url'] = 'https://another.example/steal'
        with self.assertRaises(ValueError):
            updater.render_table([item], 'example', '2026-01-02')

    def test_preserves_intro_and_contact_including_line_endings(self):
        original = 'intro 👋\r\n' + updater.START + '\r\nold\r\n' + updater.END + '\r\ncontact\r\n'
        updated = updater.replace_section(original, 'new\nrow')
        self.assertEqual(updated, 'intro 👋\r\n' + updater.START + '\r\nnew\r\nrow\r\n' + updater.END + '\r\ncontact\r\n')
        self.assertEqual(updater.replace_section(updated, 'new\nrow'), updated)

    def test_ambiguous_markers_rejected(self):
        for value in ['', updater.END + updater.START, updater.START * 2 + updater.END]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                updater.replace_section(value, 'data')

    @patch('update_open_source.subprocess.run')
    def test_pagination_uses_all_public_results(self, run):
        first = [pull(number=i) for i in range(1, 101)]
        run.side_effect = [response(first, total=101), response([pull(101)], total=101)]
        self.assertEqual(len(updater.fetch_pull_requests('example')), 101)
        self.assertEqual(run.call_count, 2)
        self.assertIn('q=is:pr is:public author:example -user:example', run.call_args.args[0])

    @patch('update_open_source.subprocess.run')
    def test_incomplete_and_over_limit_results_rejected(self, run):
        for result in [response([pull()], incomplete=True), response([pull()], total=1001)]:
            run.return_value = result
            with self.assertRaises(RuntimeError):
                updater.fetch_pull_requests('example')

    @patch('update_open_source.subprocess.run')
    def test_duplicate_or_changed_pages_rejected(self, run):
        for second in [response([pull(1)], total=2), response([pull(2)], total=3), response([], total=2)]:
            run.side_effect = [response([pull(1)], total=2), second]
            with self.assertRaises(RuntimeError):
                updater.fetch_pull_requests('example')

    @patch('update_open_source.fetch_pull_requests', side_effect=RuntimeError('API unavailable'))
    def test_api_failure_preserves_existing_readme(self, fetch):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'README.md'
            original = ('intro\n' + updater.START + '\nexisting data\n' + updater.END + '\ncontact').encode()
            path.write_bytes(original)
            with patch('sys.argv', ['update', '--login', 'example', '--readme', str(path)]):
                with self.assertRaises(RuntimeError):
                    updater.main()
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
