#!/usr/bin/env python3
"""Wrapper for Vercel deployment - handles serverless function calls"""
import sys
from pathlib import Path

# Add backend to path so imports work (resolve repository root and point to backend)
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "backend"))

from app.main import app

# Vercel expects the app to be exported
__all__ = ["app"]
