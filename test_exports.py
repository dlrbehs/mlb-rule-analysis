"""Regression and data-contract checks. Run after run_analysis.py or the notebook."""
from pathlib import Path
import csv
import hashlib
import json
import os
import unittest
from run_analysis import workspace

ROOT = Path(__file__).resolve().parent
HASH = '0e7afdd8b837d0edaca770a28817eec6613bd8255979c1be6e3f5827f4b88fd6'


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads((ROOT / 'generated/summary.json').read_text(encoding='utf-8'))
        with (ROOT / 'generated/team_review.csv').open(encoding='utf-8-sig', newline='') as f:
            cls.review = list(csv.DictReader(f))
        with (ROOT / 'generated/league_summary.csv').open(encoding='utf-8-sig', newline='') as f:
            cls.league = list(csv.DictReader(f))

    def test_source_hash(self):
        self.assertEqual(self.payload['source']['sha256'], HASH)
        if (ROOT / 'Teams.csv').exists():
            self.assertEqual(hashlib.sha256((ROOT / 'Teams.csv').read_bytes()).hexdigest(), HASH)

    def test_team_count_and_unique_key(self):
        self.assertEqual(len(self.review), 30)
        self.assertEqual(len({r['franchID'] for r in self.review}), 30)

    def test_unrecovered_count(self):
        self.assertEqual(sum(r['below_2019'] == 'True' for r in self.review), 15)

    def test_league_years(self):
        self.assertEqual([int(r['year']) for r in self.league], list(range(2010, 2026)))
        self.assertTrue(all(int(r['n_teams']) == 30 for r in self.league))

    def test_denominators(self):
        for r in self.league:
            home = float(r['total_home_games'])
            self.assertGreater(home, 0)
            self.assertAlmostEqual(float(r['attendance_per_game']), float(r['total_attendance']) / home, places=7)

    def test_comparison_counts(self):
        for r, count in zip(self.payload['comparisons'], [15, 26, 22]):
            self.assertEqual(r['n_teams'], 30)
            self.assertEqual(r['increased_teams'], count)

    def test_mean_differences(self):
        expected = {(2019, 2023): 918.4682, (2022, 2023): 2551.4700}
        for r in self.payload['comparisons']:
            key = (r['baseline_year'], r['target_year'])
            if key in expected:
                self.assertAlmostEqual(r['mean_difference'], expected[key], delta=0.001)

    def test_confidence_intervals(self):
        for r in self.payload['comparisons']:
            self.assertLess(r['ci95_low'], r['mean_difference'])
            self.assertGreater(r['ci95_high'], r['mean_difference'])
        r19, r22, _ = self.payload['comparisons']
        self.assertLess(r19['ci95_low'], 0)
        self.assertGreater(r19['ci95_high'], 0)
        self.assertGreater(r22['ci95_low'], 0)

    def test_csv_json_consistency(self):
        for base in [2019, 2022]:
            mean = sum(float(r['attendance_per_game_2023']) - float(r[f'attendance_per_game_{base}']) for r in self.review) / 30
            result = next(r for r in self.payload['comparisons'] if r['baseline_year'] == base and r['target_year'] == 2023)
            self.assertAlmostEqual(mean, result['mean_difference'], places=7)

    def test_sorted_review(self):
        vals = [float(r['change_pct_vs_2019']) for r in self.review]
        self.assertEqual(vals, sorted(vals))

    def test_model_regression(self):
        self.assertAlmostEqual(self.payload['models']['primary']['level_difference'], 2227.900, delta=0.01)
        self.assertAlmostEqual(self.payload['models']['without_2022']['level_difference'], 1214.450, delta=0.01)

    def test_metadata(self):
        self.assertEqual(self.payload['analysis']['n_team_seasons'], 480)
        self.assertEqual(self.payload['analysis']['excluded_trend_years'], [2020, 2021])
        for r in self.review + self.league:
            self.assertEqual(r['source_sha256'], HASH)
            self.assertEqual(r['generated_at_utc'], self.payload['generated_at_utc'])

    def test_wrong_input_fails_before_analysis(self):
        nb = json.loads((ROOT / 'mlb-analysis.ipynb').read_text(encoding='utf-8'))
        source = ''.join(nb['cells'][2]['source'])
        runtime = ROOT / '.runtime'
        runtime.mkdir(exist_ok=True)
        previous = Path.cwd()
        with workspace() as td:
            try:
                os.chdir(td)
                Path('Teams.csv').write_text('not the authorized dataset', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'SHA-256'):
                    exec(compile(source, '<input-validation-cell>', 'exec'), {'Path': Path})
            finally:
                os.chdir(previous)


if __name__ == '__main__':
    unittest.main(verbosity=2)
