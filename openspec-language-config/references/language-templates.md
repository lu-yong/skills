# Language Templates

Use these snippets inside `openspec/config.yaml` under `context: |`.

## Portuguese (Brazil)

```yaml
context: |
  Language: Portuguese (pt-BR)
  All artifacts must be written in Brazilian Portuguese.
```

## Spanish

```yaml
context: |
  Idioma: Español
  Todos los artefactos deben escribirse en español.
```

## Chinese (Simplified)

```yaml
context: |
  语言：中文（简体）
  所有产出物必须用简体中文撰写。
```

## Japanese

```yaml
context: |
  言語：日本語
  すべての成果物は日本語で作成してください。
```

## French

```yaml
context: |
  Langue : Français
  Tous les artefacts doivent être rédigés en français.
```

## German

```yaml
context: |
  Sprache: Deutsch
  Alle Artefakte müssen auf Deutsch verfasst werden.
```

## Technical Terms

Add terminology rules when the user wants a localized prose language but stable technical terms:

```yaml
context: |
  Language: Japanese
  Write in Japanese, but:
  - Keep technical terms like "API", "REST", and "GraphQL" in English.
  - Keep code examples, command names, identifiers, and file paths in English.
```

## Combined Project Context

Language settings can share the context block with stack and project notes:

```yaml
schema: spec-driven

context: |
  Language: Portuguese (pt-BR)
  All artifacts must be written in Brazilian Portuguese.

  Tech stack: TypeScript, React 18, Node.js 20
  Database: PostgreSQL with Prisma ORM
```
