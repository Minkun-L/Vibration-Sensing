import json
import os
import pandas as pd
import plotly.graph_objects as go

df = pd.read_csv("good_data.csv")

# Frequency columns start at index 2 (after 'id' and 'note')
freq_cols = df.columns[2:]
frequencies = [float(f) for f in freq_cols]

# Group definitions: (match_keyword, group_key, color)
# order matters — check "no" before digits to avoid false matches
GROUPS = [
    ("no", "0", "#e377c2"),
    ("1",  "1", "#1f77b4"),
    ("2",  "2", "#ff7f0e"),
    ("3",  "3", "#2ca02c"),
    ("4",  "4", "#d62728"),
]

def get_group(note: str):
    note_lower = note.lower()
    for keyword, group_key, color in GROUPS:
        if keyword in note_lower:
            return group_key, color
    return "other", "#7f7f7f"

fig = go.Figure()
seen_groups = set()

for _, row in df.iterrows():
    group_key, color = get_group(str(row["note"]))
    show_in_legend = group_key not in seen_groups
    seen_groups.add(group_key)

    fig.add_trace(go.Scatter(
        x=frequencies,
        y=row[freq_cols].astype(float).tolist(),
        mode="lines",
        name=group_key,
        legendgroup=group_key,
        legendgrouptitle_text=group_key if show_in_legend else None,
        showlegend=show_in_legend,
        line=dict(color=color),
        hovertemplate=(
            f"<b>{row['note']}</b><br>"
            "Freq: %{x} Hz<br>Amplitude: %{y:.6f}<extra></extra>"
        ),
    ))

fig.update_layout(
    title="FFT Spectra",
    xaxis_title="Frequency (Hz)",
    yaxis_title="Amplitude",
    hovermode="x unified",
    legend_title="Group",
    template="plotly_white",
)

fig.write_html("fft_plot.html", include_plotlyjs="cdn")
print("Saved to fft_plot.html")

# ── Compute per-group average FFT and save for the web app ─────────────────
group_averages = {}
for _, group_key, _ in GROUPS:
    mask = df['note'].apply(lambda n: get_group(str(n))[0] == group_key)
    subset = df[mask]
    if len(subset):
        avg = subset[freq_cols].astype(float).mean()
        group_averages[group_key] = [
            {"freq": int(f), "mag": round(float(avg[f]), 6)}
            for f in freq_cols
        ]
        print(f"Group '{group_key}': {len(subset)} samples averaged")

out_path = os.path.join("web version 2", "src", "lib", "groupAverages.json")
with open(out_path, "w") as f:
    json.dump(group_averages, f)
print(f"Group averages saved to {out_path}")

# ── Export individual samples for KNN ──────────────────────────────────────
knn_samples = []
for _, row in df.iterrows():
    group_key, _ = get_group(str(row["note"]))
    if group_key == "other":
        continue
    knn_samples.append({
        "group": group_key,
        "points": [
            {"freq": int(f), "mag": round(float(row[f]), 6)}
            for f in freq_cols
        ]
    })

knn_path = os.path.join("web version 2", "src", "lib", "knnSamples.json")
with open(knn_path, "w") as f:
    json.dump(knn_samples, f)
print(f"KNN samples saved to {knn_path} ({len(knn_samples)} samples total)")
