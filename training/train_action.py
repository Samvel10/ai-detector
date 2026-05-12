#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import torch
import torch.nn as nn
import yaml
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune video action classifier.")
    parser.add_argument("--config", default=str(ROOT / "training" / "configs" / "action.yaml"))
    args = parser.parse_args()

    with Path(args.config).open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)

    from torchvision.models.video import R3D_18_Weights, r3d_18

    device = cfg.get("device", "cuda" if torch.cuda.is_available() else "cpu")
    num_classes = int(cfg.get("num_classes", 101))
    epochs = int(cfg.get("epochs", 20))
    output_path = Path(cfg.get("output_path", ROOT / "models" / "weights" / "action" / "r3d_ucf101.pt"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    weights = R3D_18_Weights.KINETICS400_V1
    model = r3d_18(weights=weights)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    model.to(device)

    # Placeholder loader contract: replace with UCF101/HMDB51/Kinetics frame loader.
    dummy_x = torch.zeros(2, 3, 16, 112, 112)
    dummy_y = torch.zeros(2, dtype=torch.long)
    loader = DataLoader(TensorDataset(dummy_x, dummy_y), batch_size=1)

    optimizer = torch.optim.AdamW(model.parameters(), lr=float(cfg.get("learning_rate", 1e-4)))
    criterion = nn.CrossEntropyLoss()

    model.train()
    for epoch in range(epochs):
        for batch_x, batch_y in loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            optimizer.zero_grad()
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()
        print(f"epoch={epoch + 1} loss={float(loss.item()):.4f}")

    torch.save(
        {
            "state_dict": model.state_dict(),
            "labels": cfg.get("labels", []),
            "num_classes": num_classes,
        },
        output_path,
    )
    print(f"Saved action model to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
