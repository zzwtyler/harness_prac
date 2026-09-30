# Product

> **Historical design record.** The sections below preserve the earlier workbench design and are not the current runtime specification. Current behavior is defined by [README.md](../README.md): source-only extraction with Tev1 fixed-letter decisions, Qwen3.5 structured annotation, and isolated per-unit context. Thinking streams are not returned or saved; editable prompts and project background cannot override the extraction protocol or supply facts. Business operations are not executed.

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Assumption from the current brief and empty project: a dependency-free Python 3.10 server with a native HTML/CSS/JavaScript frontend, talking to the local Ollama HTTP API. The choice is intentionally easy to run locally and remains open to change if a framework is later preferred.

## Users

Primary user: a developer building a multi-stage Harness locally with Qwen through Ollama who wants to inspect each transformation from raw request to later execution artifacts.

## Product Purpose

Run any numbered Harness Stage through one inspectable workbench. Each Python Stage supplies its own prompt, JSON schema, labels, and examples while the page exposes the model's separate thinking stream and final structured output. Success means a developer can edit or add a Stage without duplicating its contract in the web layer.

## Positioning

The interface is an inspectable Harness workbench rather than a general chat client: it keeps Stage selection, reasoning trace, raw structured response, and schema-driven parsed fields visibly distinct.

## Operating Context

The app runs on a developer's machine beside Ollama. The expected model is `qwen3:4b`, served by the default local Ollama endpoint. Requests are primarily written in Chinese.

## Capabilities and Constraints

- Stream Qwen thinking and final answer separately.
- Discover numbered Python Stage Modules through a shared Interface and hot-reload their definitions.
- Require each final answer to follow its Stage's JSON schema.
- Let the user inspect and edit the Chinese system prompt and model name.
- Let the user keep an editable project background across Stage runs, with a concrete fictional café-service example and browser-local persistence.
- Report Ollama connection and model errors with a recovery action.
- No external Python packages are assumed to be installed.
- Assumption: this is a single-user local tool; authentication and remote deployment are not in scope.

## Evidence on Hand

- `core/01_user_intent.py` classifies source text into types in `core/01_user_intent_classes/`; `core/02_task.py` maps these into task types in `core/02_task_classes/`.
- Web-specific Stage metadata lives in `web/stages/` Adapters, keeping future numbered task Modules readable.
- No existing interface, brand assets, customer proof, or deployment configuration exists. Future work must not invent these.

## Product Principles

- Make model state legible: waiting, thinking, answering, done, and failed are visibly different.
- Preserve inspectability: never merge reasoning and final output into one undifferentiated block.
- Prefer precise task language over conversational decoration.
- Keep the local setup small and reversible.

## Accessibility & Inclusion

The interface should be keyboard operable, responsive, and use Chinese-first labels with clear focus and status feedback.
