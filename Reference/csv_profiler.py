"""
UE5 CSVProfiler グラフ化ツール
対象: GameThreadTime / RenderThreadTime / RHIThreadTime / GPUTime (折れ線)
      GPUMem% / SystemMem% (折れ線)

./Input フォルダ内のすべての .csv ファイルを処理し、
同名の .png を ./Output フォルダに出力する。
"""

import argparse
import glob
import os

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

# ─────────────────────────────────────────
# 設定
# ─────────────────────────────────────────
INPUT_DIR   = "./Input"
OUTPUT_DIR  = "./Output"
MAX_FRAMES  = 300   # 引数未指定時のデフォルト値

LINE_COLS = [
	"GameThreadTime",
	"RenderThreadTime",
	"RHIThreadTime",
	"GPUTime",
]

BAR_NUMERATORS   = ["GPUMem/LocalUsedMB",  "GPUMem/SystemUsedMB"]
BAR_DENOMINATORS = ["GPUMem/LocalBudgetMB", "GPUMem/SystemBudgetMB"]
BAR_LABELS       = ["GPUMem",              "SystemMem"]
BAR_COLORS       = ["#E05C5C",             "#5C9EE0"]

# 警告ライン（ms）
WARNING_MS = 33.3   # ~30 FPS
TARGET_MS  = 16.7   # ~60 FPS

# ─────────────────────────────────────────
# スタイル設定（共通・1回だけ適用）
# ─────────────────────────────────────────
plt.rcParams.update({
	"figure.facecolor" : "#1E1E2E",
	"axes.facecolor"   : "#181825",
	"axes.edgecolor"   : "#45475A",
	"axes.labelcolor"  : "#CDD6F4",
	"axes.grid"        : True,
	"grid.color"       : "#313244",
	"grid.linestyle"   : "--",
	"grid.linewidth"   : 0.5,
	"xtick.color"      : "#CDD6F4",
	"ytick.color"      : "#CDD6F4",
	"text.color"       : "#CDD6F4",
	"legend.facecolor" : "#181825",
	"legend.edgecolor" : "#45475A",
	"legend.labelcolor": "#CDD6F4",
	"font.size"        : 10,
})

LINE_PALETTE = ["#A6E3A1", "#89B4FA", "#FAB387", "#F38BA8"]


# ─────────────────────────────────────────
# グラフ生成関数
# ─────────────────────────────────────────
def process(csv_path: str, output_dir: str, max_frames: int) -> None:
	"""1つのCSVを読み込みグラフをPNGで保存する。"""

	# ヘッダーの列数を基準に読み込む
	with open(csv_path, newline="") as f:
		expected_cols = len(f.readline().split(","))

	# --- データ読み込み ---
	df = pd.read_csv(csv_path,
					header=0,
				    usecols=range(expected_cols),   # 先頭N列だけ使用
					on_bad_lines='skip',            # それでも合わない行は保険でスキップ
					)
	df = df.iloc[:max_frames].copy()
	df = df.reset_index(drop=True)
	frames = np.arange(1, len(df) + 1)

	for col in LINE_COLS + BAR_NUMERATORS + BAR_DENOMINATORS:
		df[col] = pd.to_numeric(df[col], errors="coerce")

	gpu_pct    = (df[BAR_NUMERATORS[0]] / df[BAR_DENOMINATORS[0]]) * 100
	system_pct = (df[BAR_NUMERATORS[1]] / df[BAR_DENOMINATORS[1]]) * 100

	# --- フィギュア作成 ---
	fig, (ax_line, ax_mem) = plt.subplots(
		2, 1,
		figsize=(18, 10),
		gridspec_kw={"height_ratios": [3, 2]},
		sharex=False,
	)
	fig.suptitle(
		"UE5 CSVProfiler — Performance Overview\n"
		f"({os.path.basename(csv_path)}  |  first {len(df)} frames)",
		fontsize=13,
		fontweight="bold",
		color="#CDD6F4",
		y=0.98,
	)

	# --- 上段: Thread / GPU 折れ線グラフ ---
	for col, color in zip(LINE_COLS, LINE_PALETTE):
		ax_line.plot(frames, df[col], label=col, color=color,
					 linewidth=1.2, alpha=0.9)

	ax_line.axhline(TARGET_MS,  color="#F9E2AF", linewidth=0.8,
					linestyle=":", alpha=0.8, label=f"60 FPS ({TARGET_MS} ms)")
	ax_line.axhline(WARNING_MS, color="#EBA0AC", linewidth=0.8,
					linestyle=":", alpha=0.8, label=f"30 FPS ({WARNING_MS:.1f} ms)")

	ax_line.set_ylabel("Time (ms)", fontsize=11)
	ax_line.set_title("Thread / GPU Frame Time", fontsize=11, pad=8, color="#BAC2DE")
	ax_line.legend(loc="upper right", fontsize=9, framealpha=0.7)
	ax_line.set_xlim(1, len(df))
	ax_line.yaxis.set_minor_locator(mticker.AutoMinorLocator())
	ax_line.set_xlabel("Frame", fontsize=10)

	# --- 下段: GPUMem / SystemMem 折れ線グラフ ---
	ax_mem.plot(frames, gpu_pct,
				label="GPUMem (Local Used / Budget)",
				color=BAR_COLORS[0], linewidth=1.2, alpha=0.9)
	ax_mem.plot(frames, system_pct,
				label="SystemMem (System Used / Budget)",
				color=BAR_COLORS[1], linewidth=1.2, alpha=0.9)

	ax_mem.axhline(80, color="#F9E2AF", linewidth=0.8,
					linestyle="--", alpha=0.8, label="Warning 80%")
	ax_mem.axhline(95, color="#EBA0AC", linewidth=0.8,
					linestyle="--", alpha=0.8, label="Danger  95%")

	ax_mem.set_ylabel("Usage (%)", fontsize=11)
	ax_mem.set_title("GPU Memory Usage Ratio", fontsize=11, pad=8, color="#BAC2DE")
	ax_mem.set_ylim(0, 110)
	ax_mem.yaxis.set_major_formatter(mticker.PercentFormatter())
	ax_mem.set_xlabel("Frame", fontsize=10)
	ax_mem.legend(loc="upper right", fontsize=9, framealpha=0.7)
	ax_mem.set_xlim(1, len(df))

	# --- 統計サマリー ---
	summary_lines = []
	for col, color in zip(LINE_COLS, LINE_PALETTE):
		s = df[col].dropna()
		summary_lines.append(
			f"[{col}]  avg={s.mean():.2f}  max={s.max():.2f}  min={s.min():.2f} ms"
		)
	summary_lines.append(
		f"[GPUMem]     avg={gpu_pct.mean():.1f}%  max={gpu_pct.max():.1f}%"
	)
	summary_lines.append(
		f"[SystemMem]  avg={system_pct.mean():.1f}%  max={system_pct.max():.1f}%"
	)

	fig.text(
		0.01, 0.01,
		"\n".join(summary_lines),
		fontsize=8,
		color="#BAC2DE",
		verticalalignment="bottom",
		fontfamily="monospace",
	)

	plt.tight_layout(rect=[0, 0.08, 1, 0.96])

	# --- 保存 ---
	stem = os.path.splitext(os.path.basename(csv_path))[0]
	output_path = os.path.join(output_dir, stem + ".png")
	plt.savefig(output_path, dpi=150, bbox_inches="tight",
				facecolor=fig.get_facecolor())
	plt.close(fig)
	print(f"  ✅ 保存完了: {output_path}")


# ─────────────────────────────────────────
# メイン: Input フォルダ内の全CSVを処理
# ─────────────────────────────────────────
def main() -> None:
	parser = argparse.ArgumentParser(
		description="UE5 CSVProfiler グラフ化ツール",
	)
	parser.add_argument(
		"-f", "--frames",
		type=int,
		default=MAX_FRAMES,
		metavar="N",
		help=f"グラフ化するフレーム数（デフォルト: {MAX_FRAMES}）",
	)
	args = parser.parse_args()
	max_frames = args.frames

	if max_frames <= 0:
		print("❌ フレーム数は1以上を指定してください。")
		return

	csv_files = sorted(glob.glob(os.path.join(INPUT_DIR, "*.csv")))

	if not csv_files:
		print(f"⚠️  CSVファイルが見つかりません: {INPUT_DIR}")
		return

	os.makedirs(OUTPUT_DIR, exist_ok=True)
	print(f"📂 対象ファイル数: {len(csv_files)} 件  |  フレーム数: {max_frames}")

	success, failure = 0, 0
	for csv_path in csv_files:
		print(f"🔄 処理中: {os.path.basename(csv_path)}")
		try:
			process(csv_path, OUTPUT_DIR, max_frames)
			success += 1
		except Exception as e:
			print(f"  ❌ エラー: {e}")
			failure += 1

	print(f"\n📊 完了 — 成功: {success} 件 / 失敗: {failure} 件")


if __name__ == "__main__":
	main()
