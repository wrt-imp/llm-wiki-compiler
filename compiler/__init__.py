"""LLM Wiki Compiler.

Implemented stages:

1. ``compiler.parser`` - PDF / Markdown / TXT -> ``Document`` (text + parse metadata)
2. ``compiler.document`` - ``Document`` -> sections (Document Model)
3. ``compiler.extraction`` - ``Document`` -> ``Knowledge IR`` via an LLM
   (with ``compiler.llm`` providing the model client and ``compiler.knowledge``
   defining the IR)
4. ``compiler.merge`` - ``Knowledge IR``s -> one ``KnowledgeBase``
   (Semantic Merge: normalize, candidate matching, LLM judge, merge)
5. ``compiler.wiki`` - ``KnowledgeBase`` -> Markdown wiki pages
   (Wiki Generator: deterministic rendering, no links, no LLM)
6. ``compiler.linker`` - ``WikiBuild`` -> linked wiki
   (Link Resolver: relative markdown links, markdown aware, no dead links)
7. ``compiler.search`` - wiki directory -> keyword search
   (Search: markdown index, deterministic ranking, snippets, stdlib only)
8. ``compiler.graph`` - ``KnowledgeBase`` -> ``Graph``
   (Graph: nodes for entities/concepts, edges for relations and complete facts)
9. ``compiler.lint`` - compiled results -> ``LintResult``
   (Lint: deterministic, read only quality and structure checks)

That is the whole pipeline: parse, structure, extract, merge, generate, link,
search, graph and lint.

There is a second entry point as well: ``.lw`` files are Mermaid graph sources
that compile straight into the same ``Graph`` (no Knowledge IR involved)::

    python -m compiler examples/example.lw      # graph + local web UI

See ``compiler.lw`` for the parsing and adapter layer and ``compiler.web`` for
the browser UI.
"""

__version__ = "0.1.0"
