# Telegram Chat Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add chat-level Telegram settings for price, area, bedrooms, and disputed listings, then apply them to `Новые`.

**Architecture:** Persist one settings row and one pending-input row per chat in SQLite. Keep parsing and query selection in the bot layer so `Новые` respects current chat filters without disturbing saved listings or the scraping pipeline.

**Tech Stack:** Python 3.12, SQLite, Telegram Bot API, pytest

---
