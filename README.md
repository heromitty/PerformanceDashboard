# PerformanceDashboard

UE5 CSVProfilerのサニタイズ済みデータを使って、Revision / Levelごとの統計、Frame Graph、Performance Heatmapを表示するStreamlit Dashboardです。

## データフロー

```text
RawData/
  ↓ python sanitize_csv.py
SanitizedData/
  ├─ DashboardのRevision / Level / CSV統計入力
  ├─ python generate_graphs.py
  │    ↓
  │  GraphCache/
  └─ python generate_heatmaps.py
       ↓
     HeatmapCache/
          ↓
     Streamlit Dashboard
```

`RawData/`、`SanitizedData/`、`HeatmapCache/`はGit管理対象外です。Dashboardは`SanitizedData/`を直接読み込み、Revision / Levelの検出とCSV統計の計算を行います。グラフとヒートマップは事前生成されたCache画像を表示します。

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

4. Performance Heatmapを生成します。

   ```text
   python generate_heatmaps.py
   ```

5. Dashboardを起動します。

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
