# PerformanceDashboard

UE5 CSVProfilerのサニタイズ済みデータを使って、Revision / Levelごとの統計、Frame Graph、Performance Heatmapを表示するStreamlit Dashboardです。

## データフロー

```text
RawData/
  ↓ python sanitize_csv.py
SanitizedData/
  ├─ DashboardのRevision / Level列挙入力
  ├─ python generate_graphs.py
  │    ↓
  │  GraphCache/
  ├─ python generate_heatmaps.py
  │    ↓
  │  HeatmapCache/
  └─ python generate_statistics.py
       ↓
     StatisticsCache/
          ↓
     Streamlit Dashboard
```

`RawData/`、`SanitizedData/`、`HeatmapCache/`、`StatisticsCache/`はGit管理対象外です。Dashboardは`SanitizedData/`からRevision / Levelを列挙し、統計値は事前生成された`StatisticsCache/`から読み込みます。DashboardはCSVの統計計算やStatisticsCacheの生成を行いません。グラフとヒートマップも事前生成されたCache画像を表示します。

## 実行手順

1. CSVProfilerのCSVを`RawData/`以下へ配置します。
2. CSVをサニタイズします。

   ```text
   python sanitize_csv.py
   ```

3. Frame Graphを生成します。

   ```text
   python generate_graphs.py
   ```

   入力元を指定する場合は`--input-data`を使用できます。

   ```text
   python generate_graphs.py --input-data <path>
   ```

   既存のGraphCacheを35ms上限・超過マーカー付きで更新する場合は`--force`を使用します。

   ```text
   python generate_graphs.py --force
   ```

4. Performance Heatmapを生成します。

   ```text
   python generate_heatmaps.py
   ```

5. StatisticsCacheを生成します。

   ```text
   python generate_statistics.py
   ```

   初回は全CSVを処理し、2回目以降は有効なJSONをスキップして、未生成・破損・仕様不一致のキャッシュだけを生成します。入力や出力先を指定する場合は`--input-data`と`--statistics-cache`を使用できます。

6. Dashboardを起動します。

   ```text
   streamlit run app.py
   ```

## Cache

Frame Graphは以下へ保存されます。

```text
GraphCache/<Revision>/<Level>.png
```

Performance Heatmapは以下へ保存されます。

```text
HeatmapCache/<Revision>/<Level>-FrameTime.png
HeatmapCache/<Revision>/<Level>-GameThreadTime.png
HeatmapCache/<Revision>/<Level>-RenderThreadTime.png
HeatmapCache/<Revision>/<Level>-GPUTime.png
```

統計値は以下へRevision / Level単位で保存されます。

```text
StatisticsCache/<Revision>/<Level>.json
```

StatisticsCacheにはMean / Median / Max / P95、ValidFrameCount、GameThread / RenderThread / GPUの超過回数・超過率を保存します。JSONが不足・破損している場合、Dashboardは該当LevelをN/A表示し、対象CSV件数を警告します。`generate_statistics.py`を再実行してください。

運用上、一度生成したSanitizedDataのCSVは更新しない前提です。CSVを例外的に差し替えた場合は、対応する`StatisticsCache/<Revision>/<Level>.json`を手動削除してから`python generate_statistics.py`を実行してください。元CSVが削除された場合、対応するキャッシュは自動削除せず、Dashboardの表示対象から除外します。
