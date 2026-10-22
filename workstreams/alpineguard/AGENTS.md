# Coding and Documenting Guidelines

All agents and contributors working in this repository must strictly adhere to the following guidelines:

1. **File per Feature / Modular Splitting**:
   - Create a file per feature or closely related set of features.
   - Split code into separate files as much as possible to keep components focused and modular.

2. **Function Docstrings**:
   - Add clear, descriptive docstrings to every function and method explaining its purpose, parameters, return values, and possible errors/exceptions.

3. **Detailed File Header Comment**:
   - Start each file with an in-depth comment/docstring explaining what the feature is about, its architecture, and its different use cases.

4. **Living `Design.md` Document**:
   - Maintain a `Design.md` file at the root of the repository documenting all the features of the application, their architectural role, and relationships.
   - Keep `Design.md` continuously updated as new features are planned, added, or modified.

5. **Function & GenAI Call Logging**:
   - Log at `INFO` level all function calls with their parameters.
   - Log all GenAI / LLM calls with all parameters (model used, prompt, configuration) and outputs.
   - Always strip large inline data (e.g., base64 images, raw audio/binary payloads) from log entries to keep logs clean and readable.

6. **Centralized Configuration**:
   - Group all configurable items (e.g., model names, endpoints, temperature/top_p, thresholds, constants) in a centralized configuration file (e.g., `config.py` or equivalent config module).



<!-- entire-agent:begin -->
Read .entire/agent-guide.md for this repository's workflow, source inspection, and verification guidance.
@.entire/agent-guide.md
<!-- entire-agent:end -->
