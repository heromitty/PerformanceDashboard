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

## 開発環境

- Windows / PowerShellで開発します。
- Python 3.13を使用します。
- WindowsAppsのPythonエイリアスは使用せず、通常インストール版Pythonを使用します。
- Python実行ファイルは次のように`$env:USERPROFILE`を基準に解決します。

  ```powershell
  $Python = Join-Path $env:USERPROFILE 'AppData\Local\Programs\Python\Python313\python.exe'
  ```

- 依存ライブラリは`requirements.txt`に従います。
- 不要なライブラリのインストールは行いません。依存不足時は理由を報告し、必要な承認を得ます。

## テスト

- 変更後は構文チェックと関連する自動テストを実行します。
- 基本コマンドは次のとおりです。

  ```powershell
  $Python = Join-Path $env:USERPROFILE 'AppData\Local\Programs\Python\Python313\python.exe'
  & $Python -B -m unittest discover -s tests -p 'test_*.py' -v
  ```

- テスト失敗時は原因を調査します。
- テスト未実行の場合は理由を報告します。
- 実CSVでの最終動作確認はユーザーが行います。

## Git運用

- `main`に直接Commitしません。機能・文書などの作業ごとに作業ブランチを作成します。
- 作業開始前に`git status -sb`で状態を確認します。
- 既存の未追跡ファイルを勝手に変更・削除しません。
- `git add .`や`git add -A`は原則使用せず、変更したファイルだけを明示的にStageします。
- Force Pushは禁止です。
- GitHubへのPushには事前承認が必要です。
- PR作成はユーザーの承認を得てから行います。
- `main`へのマージはユーザーが実施します。
- サンドボックス外での実行や権限昇格が必要な場合は、対象コマンドと理由を明示し、操作ごとにユーザーの承認を求めます。承認が得られない場合は実行せず、代替方法を報告します。

## GitHub CLI

- GitHub CLIは次の実行ファイルを使用します。

  ```powershell
  $Gh = 'C:\Program Files\GitHub CLI\gh.exe'
  ```

- PATHで認識できない場合は絶対パスで実行します。
- GitHub CLIのkeyring認証がサンドボックス内で失敗する場合は、該当コマンドのみ個別の権限承認を求めます。
- 認証トークンや秘密情報を取得・表示・コピーしません。
- サンドボックスを恒久的に無効化しません。

## 作業完了時の報告

- 変更ファイル
- 変更内容
- 実施したテストと結果
- Gitブランチ
- Commit ID
- Push状態
- PR番号・URL（作成した場合）
- 未解決の問題
