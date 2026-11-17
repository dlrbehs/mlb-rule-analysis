"""Execute the notebook, validate its exports, and optionally sync a portfolio checkout.

Usage: python run_analysis.py [--site-dir ../dlrbehs.github.io]
No global kernelspec is installed. Notebook computation is the single source of truth.
"""
from pathlib import Path
import argparse
import html
import json
import os
import shutil
import sys
from contextlib import contextmanager
from uuid import uuid4
import unittest
import nbformat
from IPython.core.interactiveshell import InteractiveShell
from IPython.utils.capture import capture_output

ROOT = Path(__file__).resolve().parent
SECTIONS = [
    ('setup', '실행 환경'), ('source', 'Lahman 2025 데이터와 SHA-256 검증'),
    ('quality', '분석 표본과 데이터 품질'), ('identifiers', '같은 구단의 식별자 매칭'),
    ('total', '연도별 총관중과 경기당 관중'), ('growth', '총관중 증가율과 증가 구단 수'),
    ('baseline', '코로나19 이전과 비교'), ('trend', '시즌별 관중 추이'),
    ('paired', '세 시즌 비교와 조건부 95% 신뢰구간'), ('declines', '2019년 미회복 구단'),
    ('team-differences', '구단별 관중 변화'), ('distribution', '변화량 분포와 정규 Q-Q 도표'),
    ('spread', '증가 분포와 극단값 민감도'), ('model', '공통 추세 수준 변화 모형'),
    ('diagnostics', '잔차 자기상관과 HAC'), ('fitted', '관측값과 회귀 적합선'),
    ('sensitivity', '추세와 2022년 포함 여부 민감도'), ('level', '수준 차이의 크기'),
    ('exports', '검토표·리그 집계·핵심 수치 자동 내보내기')
]


@contextmanager
def workspace():
    directory = ROOT / '.runtime' / uuid4().hex
    directory.mkdir(parents=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


def render_notebook(nb):
    out = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           '<title>MLB 분석 코드 · GyuDon Lee</title><link rel="stylesheet" href="style.css">',
           '</head><body class="paper notebook"><a class="skip" href="#main">본문으로 건너뛰기</a>',
           '<header class="reader-nav"><div class="wrap"><a href="mlb.html">← 프로젝트로</a>',
           '<span class="mono">GYUDON LEE</span></div></header><main id="main" class="wrap article">',
           '<p class="kicker">PYTHON NOTEBOOK</p><h1>분석 코드와 실행 결과</h1>',
           '<p class="lead">규칙이 관중을 불렀는가 · 이규돈</p>',
           '<p>고정 버전 입력의 SHA-256을 검사하고 모든 코드 셀을 순서대로 실행한 결과입니다. ',
           '관측된 30개 구단의 변화와 확률모형 기반 추론을 구분합니다. ',
           'p값·신뢰구간은 구단 간 독립성 등 가정에 조건부이며 정책의 인과효과가 아닙니다.</p>',
           '<p><a href="mlb-analysis.ipynb" download>실행용 노트북</a> · ',
           '<a href="requirements.txt" download>고정 패키지 버전</a> · ',
           '<a href="https://github.com/dlrbehs/mlb-rule-analysis">저장소와 재현 방법 ↗</a></p>',
           '<p>바로가기 · <a href="#paired">평균 차이와 신뢰구간</a> · <a href="#spread">극단값</a> · ',
           '<a href="#diagnostics">DW와 HAC</a> · <a href="#sensitivity">민감도</a> · <a href="#exports">내보내기</a></p>']
    for i, cell in enumerate(c for c in nb.cells if c.cell_type == 'code'):
        ident, title = SECTIONS[i]
        out.append(f'<section class="cell" id="{ident}"><h2>셀 {i+1} · {title}</h2>')
        out.append('<pre><code>' + html.escape(cell.source) + '</code></pre>')
        for output in cell.get('outputs', []):
            if output.output_type == 'error':
                raise RuntimeError('Refusing to publish a notebook containing errors')
            if output.output_type == 'stream':
                out.append('<pre class="result">' + html.escape(output.text) + '</pre>')
            else:
                data = output.get('data', {})
                if 'image/png' in data:
                    out.append(f'<img src="data:image/png;base64,{data["image/png"]}" alt="セル {i+1} 분석 그래프" style="max-width:100%;height:auto">'.replace('セル', '셀'))
                elif 'text/html' in data:
                    out.append('<div class="table-scroll">' + data['text/html'] + '</div>')
                elif 'text/plain' in data:
                    out.append('<pre class="result">' + html.escape(data['text/plain']) + '</pre>')
        out.append('</section>')
    out.append('<footer><a href="mlb.html">← 프로젝트로</a></footer></main></body></html>')
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site-dir', type=Path)
    args = parser.parse_args()
    os.chdir(ROOT)
    nb = nbformat.read(ROOT / 'mlb-analysis.ipynb', as_version=4)
    for cell in nb.cells:
        if cell.cell_type == 'code':
            cell.outputs = []
            cell.execution_count = None
    runtime_root = ROOT / '.runtime'
    runtime_root.mkdir(exist_ok=True)
    # A fresh CLI process uses one IPython namespace without opening kernel ports.
    # This preserves notebook expressions, rich displays and inline figures.
    shell = InteractiveShell.instance(user_ns={})
    import matplotlib
    matplotlib.use('module://matplotlib_inline.backend_inline')
    from matplotlib_inline.backend_inline import configure_inline_support
    configure_inline_support(shell, 'inline')
    counter = 0
    for cell in nb.cells:
        if cell.cell_type != 'code':
            continue
        counter += 1
        with capture_output() as captured:
            result = shell.run_cell(cell.source, store_history=True)
        if not result.success:
            raise RuntimeError(f'Notebook cell {counter} failed: ' + captured.stdout + captured.stderr)
        outputs = []
        if captured.stdout:
            outputs.append(nbformat.v4.new_output('stream', name='stdout', text=captured.stdout))
        if captured.stderr:
            outputs.append(nbformat.v4.new_output('stream', name='stderr', text=captured.stderr))
        for rich in captured.outputs:
            outputs.append(nbformat.v4.new_output('display_data', data=rich.data, metadata=rich.metadata))
        cell.outputs = outputs
        cell.execution_count = counter
        print(f'Executed cell {counter}', flush=True)
    nb.metadata.language_info.version = sys.version.split()[0]
    nbformat.write(nb, ROOT / 'mlb-analysis.ipynb')
    suite = unittest.defaultTestLoader.discover(str(ROOT), pattern='test_exports.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit('Validation failed; site was not synchronized.')
    rendered = render_notebook(nb)
    (ROOT / 'notebook.html').write_text(rendered, encoding='utf-8')
    if args.site_dir:
        site = args.site_dir.resolve()
        if not (site / 'index.html').is_file():
            raise SystemExit('site-dir must be an existing portfolio checkout with index.html')
        (site / 'generated').mkdir(exist_ok=True)
        for name in ['mlb-analysis.ipynb', 'notebook.html', 'requirements.txt']:
            shutil.copy2(ROOT / name, site / name)
        for name in ['league_summary.csv', 'team_review.csv', 'summary.json']:
            shutil.copy2(ROOT / 'generated' / name, site / 'generated' / name)
        print('Portfolio outputs synchronized.')
    print(f'Executed {len(SECTIONS)} code cells and passed {result.testsRun} tests.')


if __name__ == '__main__':
    main()
