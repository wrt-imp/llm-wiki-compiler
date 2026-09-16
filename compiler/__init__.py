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

Search, graph and lint are intentionally not implemented yet.
"""

__version__ = "0.1.0"
