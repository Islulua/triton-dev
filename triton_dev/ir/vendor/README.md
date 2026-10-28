# TritonParse location parser

Vendored from https://github.com/meta-pytorch/tritonparse at commit
`a573a10384ec519dcc485a9c3c7354f35538f4e8`, file `tritonparse/parse/ir_parser.py`.
BSD-3-Clause license is preserved in LICENSE. Local modification: use Python's
standard logging.getLogger instead of tritonparse.tp_logger.get_logger, avoiding
Triton/PyTorch dependencies in the API process. All other code is upstream.

The normalized document and UI use source locations; these are associations,
not a complete compiler transformation/provenance graph.
