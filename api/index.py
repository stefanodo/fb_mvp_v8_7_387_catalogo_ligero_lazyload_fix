#!/usr/bin/env python3
"""Wrapper for Vercel deployment - handles serverless function calls"""
import sys
from pathlib import Path

# Add backend to path so imports work
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.main import app

# Vercel expects the app to be exported
__all__ = ["app"]
