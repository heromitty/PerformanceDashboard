# PerformanceDashboard 開発ガイド

- UE5 CSVProfilerを扱うPython + Streamlitプロジェクトです。
- Revisionフォルダ名とLevel名を論理キーとして扱います。
- SQLiteは使用しません。
- `RawData/`は生のCSVProfilerデータ置き場です。Git管理対象外です。
- `sanitize_csv.py`で`RawData/`をサニタイズし、`SanitizedData/`へ出力します。
- `SanitizedData/`がDashboard、`generate_graphs.py`、`generate_heatmaps.py`の正式な入力元です。Git管理対象外です。
- `GraphCache/`は`generate_graphs.py`が事前生成するFrame Graphの置き場です。
- `HeatmapCache/`は`generate_heatmaps.py`が事前生成するPerformance Heatmapの置き場です。Git管理対象外です。
- DashboardはCache画像を表示するだけで、グラフやHeatmapを生成しません。
- CSVの`EVENTS`が`Cmd:`で始まる行はFrame統計から除外します。
- 過度なクラス設計や大規模なリファクタリングは避けます。
- 実計測データをTracked Fileへコピーしたり、`RawData/`、`SanitizedData/`、`HeatmapCache/`をステージしたりしません。
