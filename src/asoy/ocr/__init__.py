"""OCR Layer: RapidOCR on both tiers, the tier selecting the backend (ARCHITECTURE section 4.5).

One engine across both tiers, so OCR output differs by speed rather than by model (ADR-019).
Tesseract and PaddleOCR were removed and must not come back without reopening that ADR.

The tier is meant to select ONNX Runtime on CUDA over ONNX Runtime on CPU. onnxruntime-gpu is not
installed, so both tiers run the CPU backend today; the GPU tier's advantage is currently in
description quality only, not in speed (ADR-021).
"""
