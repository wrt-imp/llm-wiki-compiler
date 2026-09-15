"""LLM Wiki Compiler.

Implemented stages:

1. ``compiler.parser`` - PDF / Markdown / TXT -> ``Document`` (text + parse metadata)
2. ``compiler.document`` - ``Document`` -> sections (Document Model)
3. ``compiler.extraction`` - ``Document`` -> ``Knowledge IR`` via an LLM
   (with ``compiler.llm`` providing the model client and ``compiler.knowledge``
   defining the IR)
4. ``compiler.merge`` - ``Knowledge IR``s -> one ``KnowledgeBase``
   (Semantic Merge: normalize, candidate matching, LLM judge, merge)

Wiki generation, link resolution, search, graph and lint are intentionally not
implemented yet.
"""

__version__ = "0.1.0"
