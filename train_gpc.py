"""
train_gpc.py  —  Gaussian Process Classifier for liner thickness
================================================================
Uses history.json to train a GPC that predicts thickness class
(0.25" / 0.50" / 0.75" / 1.00") from vibration features.

Two feature modes (set FEATURE_MODE below):
  'scalar'  — 7 hand-crafted features
  'fft'     — 160-bin FFT magnitude vector (PCA-reduced)

Usage:
    python3 train_gpc.py
"""

import json
import re
import numpy as np
from sklearn.gaussian_process import GaussianProcessClassifier
from sklearn.gaussian_process.kernels import RBF, ConstantKernel as C
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.decomposition import PCA
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

# ── Config ──────────────────────────────────────────────────────────────────
HISTORY_PATH  = 'history.json'
FEATURE_MODE  = 'scalar'   # 'scalar' or 'fft'
FFT_N_COMPONENTS = 20      # PCA components when FEATURE_MODE='fft'
CV_FOLDS      = 5
RANDOM_STATE  = 42
# ────────────────────────────────────────────────────────────────────────────

SCALAR_FIELDS = [
    'primaryFreq', 'spectralCentroid', 'rmsAcceleration',
    'secondFreq', 'freqRatio', 'qFactor', 'dampingRatio',
]


def parse_thickness(note: str):
    """Extract numeric thickness (inches) from a note string, or return None."""
    if not note:
        return None
    n = note.lower().strip()
    m = re.search(r'(\d*\.?\d+)"', n)
    if m:
        v = float(m.group(1))
        for ref in [0.25, 0.50, 0.75, 1.00]:
            if abs(v - ref) < 0.05:
                return ref
    if re.search(r'1.{0,3}(quarter|quart|qua)', n) or '1/4' in n:
        return 0.25
    if re.search(r'2.{0,3}(quarter|quart|qua)', n) or '2/4' in n:
        return 0.50
    if re.search(r'3.{0,3}(quarter|quart|qua)', n) or '3/4' in n:
        return 0.75
    if re.search(r'4.{0,3}(quarter|quart|qua)', n) or '4/4' in n:
        return 1.00
    return None


def load_data():
    with open(HISTORY_PATH) as f:
        records = json.load(f)

    X_scalar, X_fft, y = [], [], []

    # Collect all FFT frequencies from first record with fftPoints
    ref_freqs = None
    for r in records:
        if r.get('fftPoints'):
            ref_freqs = [p['freq'] for p in r['fftPoints']]
            break

    for r in records:
        thickness = parse_thickness(r.get('note', ''))
        if thickness is None:
            continue
        # Scalar features — skip if any is missing
        scalar_vals = [r.get(f) for f in SCALAR_FIELDS]
        if any(v is None for v in scalar_vals):
            continue
        # FFT features — skip if missing or wrong length
        fft_pts = r.get('fftPoints', [])
        if len(fft_pts) != len(ref_freqs):
            continue

        X_scalar.append(scalar_vals)
        X_fft.append([p['mag'] for p in fft_pts])
        y.append(thickness)

    X_scalar = np.array(X_scalar, dtype=float)
    X_fft    = np.array(X_fft,    dtype=float)
    y        = np.array(y,         dtype=float)
    return X_scalar, X_fft, y, ref_freqs


def build_features(X_scalar, X_fft, scaler_s, scaler_f, pca, fit=True):
    if FEATURE_MODE == 'scalar':
        if fit:
            return scaler_s.fit_transform(X_scalar)
        return scaler_s.transform(X_scalar)
    else:  # 'fft'
        if fit:
            Xf = scaler_f.fit_transform(X_fft)
            return pca.fit_transform(Xf)
        Xf = scaler_f.transform(X_fft)
        return pca.transform(Xf)


def main():
    print(f"Feature mode : {FEATURE_MODE}")
    print(f"Loading data from {HISTORY_PATH} …")
    X_scalar, X_fft, y, ref_freqs = load_data()

    classes, counts = np.unique(y, return_counts=True)
    print(f"Samples      : {len(y)} total")
    for c, n in zip(classes, counts):
        print(f"  {c:.2f}\"  →  {n} samples")
    print()

    # ── Preprocessing ────────────────────────────────────────────────────────
    scaler_s = StandardScaler()
    scaler_f = StandardScaler()
    pca      = PCA(n_components=FFT_N_COMPONENTS, random_state=RANDOM_STATE)

    X = build_features(X_scalar, X_fft, scaler_s, scaler_f, pca, fit=True)

    le = LabelEncoder()
    y_enc = le.fit_transform(y)
    label_names = [f'{c:.2f}"' for c in le.classes_]

    if FEATURE_MODE == 'fft':
        print(f"PCA variance explained ({FFT_N_COMPONENTS} components): "
              f"{pca.explained_variance_ratio_.sum()*100:.1f}%")

    # ── GPC kernel ───────────────────────────────────────────────────────────
    kernel = C(1.0, (1e-2, 1e2)) * RBF(
        length_scale=np.ones(X.shape[1]),
        length_scale_bounds=(1e-2, 1e2),
    )
    gpc = GaussianProcessClassifier(
        kernel=kernel,
        n_restarts_optimizer=3,
        random_state=RANDOM_STATE,
        max_iter_predict=200,
    )

    # ── Cross-validation ─────────────────────────────────────────────────────
    print(f"Running {CV_FOLDS}-fold stratified cross-validation …")
    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    y_pred = cross_val_predict(gpc, X, y_enc, cv=cv)

    print("\n── Classification Report ────────────────────────────────")
    print(classification_report(y_enc, y_pred, target_names=label_names))

    # ── Confusion matrix ─────────────────────────────────────────────────────
    cm = confusion_matrix(y_enc, y_pred)
    fig, ax = plt.subplots(figsize=(5, 4))
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=label_names)
    disp.plot(ax=ax, colorbar=False, cmap='Blues')
    ax.set_title(f'GPC Confusion Matrix ({FEATURE_MODE} features, {CV_FOLDS}-fold CV)')
    plt.tight_layout()
    plt.savefig('gpc_confusion_matrix.png', dpi=150)
    print("Confusion matrix saved → gpc_confusion_matrix.png")

    # ── Train final model on all data ─────────────────────────────────────────
    print("\nTraining final model on all data …")
    gpc.fit(X, y_enc)
    print(f"Optimized kernel: {gpc.kernel_}")

    # ── Feature importance (scalar mode only) ─────────────────────────────────
    if FEATURE_MODE == 'scalar':
        # Multiclass GPC uses one-vs-rest internally → CompoundKernel with one
        # C*RBF sub-kernel per binary problem. Average length_scale across all.
        sub_kernels = getattr(gpc.kernel_, 'kernels', [gpc.kernel_])
        ls_list = []
        for k in sub_kernels:
            try:
                ls_list.append(k.k2.length_scale)
            except AttributeError:
                pass
        if ls_list:
            length_scales = np.mean(ls_list, axis=0)
        else:
            length_scales = np.ones(len(SCALAR_FIELDS))
        # Shorter length scale → feature varies more relative to scale → more informative
        importance = 1.0 / length_scales
        importance /= importance.sum()
        print("\n── Feature Importance (1/length_scale, normalized) ──────")
        for name, imp in sorted(zip(SCALAR_FIELDS, importance), key=lambda x: -x[1]):
            bar = '█' * int(imp * 40)
            print(f"  {name:<22}  {imp:.3f}  {bar}")

        fig2, ax2 = plt.subplots(figsize=(7, 3))
        sorted_pairs = sorted(zip(SCALAR_FIELDS, importance), key=lambda x: x[1])
        names_sorted = [p[0] for p in sorted_pairs]
        imp_sorted   = [p[1] for p in sorted_pairs]
        ax2.barh(names_sorted, imp_sorted, color='steelblue')
        ax2.set_xlabel('Relative importance (1/length_scale)')
        ax2.set_title('GPC feature importance')
        plt.tight_layout()
        plt.savefig('gpc_feature_importance.png', dpi=150)
        print("Feature importance saved → gpc_feature_importance.png")

    # ── 2-D decision boundary (PCA projection, scalar mode) ──────────────────
    if FEATURE_MODE == 'scalar':
        pca2 = PCA(n_components=2, random_state=RANDOM_STATE)
        X2 = pca2.fit_transform(X)

        x_min, x_max = X2[:, 0].min() - 1, X2[:, 0].max() + 1
        y_min, y_max = X2[:, 1].min() - 1, X2[:, 1].max() + 1
        xx, yy = np.meshgrid(np.linspace(x_min, x_max, 120),
                             np.linspace(y_min, y_max, 120))
        grid = np.c_[xx.ravel(), yy.ravel()]

        kernel2 = C(1.0, (1e-2, 1e2)) * RBF(1.0, (1e-2, 1e2))
        gpc2 = GaussianProcessClassifier(kernel=kernel2, random_state=RANDOM_STATE,
                                          max_iter_predict=200)
        gpc2.fit(X2, y_enc)
        Z = gpc2.predict(grid).reshape(xx.shape)

        colors = ['#60a5fa', '#34d399', '#f472b6', '#fbbf24']
        fig3, ax3 = plt.subplots(figsize=(6, 5))
        ax3.contourf(xx, yy, Z, alpha=0.25, levels=len(classes)-1, colors=colors[:len(classes)])
        for i, (cls, name) in enumerate(zip(range(len(classes)), label_names)):
            mask = y_enc == cls
            ax3.scatter(X2[mask, 0], X2[mask, 1], label=name,
                        color=colors[i], edgecolors='k', linewidths=0.4, s=40)
        ax3.set_xlabel('PC1')
        ax3.set_ylabel('PC2')
        ax3.set_title('GPC decision boundary (PCA 2D projection)')
        ax3.legend(fontsize=8)
        plt.tight_layout()
        plt.savefig('gpc_decision_boundary.png', dpi=150)
        print("Decision boundary saved → gpc_decision_boundary.png")

    plt.show()
    print("\nDone.")


if __name__ == '__main__':
    main()
