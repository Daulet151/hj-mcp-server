"""
Schema documentation loader from YAML files.
"""
import yaml
from pathlib import Path
from typing import Dict, List, Any
from utils.logger import setup_logger

logger = setup_logger(__name__)


class SchemaLoader:
    """Loads and manages database schema documentation from YAML files."""

    def __init__(self, docs_path: Path):
        """
        Initialize schema loader.

        Args:
            docs_path: Path to the docs directory containing YAML files
        """
        self.docs_path = Path(docs_path)
        self.schema = {
            "tables": {},
            "semantic": {},
            "glossary": {},
            "examples": []
        }

    def load_all(self) -> Dict[str, Any]:
        """
        Load all schema documentation.

        Returns:
            Dictionary containing all schema information
        """
        logger.info("Loading schema documentation from %s", self.docs_path)

        try:
            self._load_tables()
            self._load_semantic()
            self._load_glossary()
            self._load_examples()

            logger.info(
                "Schema loaded successfully: %d tables, %d examples",
                len(self.schema["tables"]),
                len(self.schema["examples"])
            )

            return self.schema

        except Exception as e:
            logger.error("Failed to load schema: %s", str(e))
            raise

    def _load_tables(self):
        """Load table definitions from docs/tables/*.yml"""
        tables_path = self.docs_path / "tables"

        if not tables_path.exists():
            logger.warning("Tables directory not found: %s", tables_path)
            return

        for table_file in tables_path.glob("*.yml"):
            try:
                with open(table_file, encoding='utf-8') as f:
                    table_data = yaml.safe_load(f)
                    if table_data and "table" in table_data:
                        self.schema["tables"][table_data["table"]] = table_data
                        logger.debug("Loaded table: %s", table_data["table"])
            except Exception as e:
                logger.error("Error loading table file %s: %s", table_file, str(e))

    def _load_semantic(self):
        """Load semantic relationships from docs/semantic.yml"""
        semantic_file = self.docs_path / "semantic.yml"

        if not semantic_file.exists():
            logger.warning("Semantic file not found: %s", semantic_file)
            return

        try:
            with open(semantic_file, encoding='utf-8') as f:
                self.schema["semantic"] = yaml.safe_load(f) or {}
                logger.debug("Loaded semantic relationships")
        except Exception as e:
            logger.error("Error loading semantic file: %s", str(e))

    def _load_glossary(self):
        """Load business glossary from docs/glossary.yml"""
        glossary_file = self.docs_path / "glossary.yml"

        if not glossary_file.exists():
            logger.warning("Glossary file not found: %s", glossary_file)
            return

        try:
            with open(glossary_file, encoding='utf-8') as f:
                self.schema["glossary"] = yaml.safe_load(f) or {}
                logger.debug("Loaded glossary")
        except Exception as e:
            logger.error("Error loading glossary file: %s", str(e))

    def _load_examples(self):
        """Load query examples from docs/examples/*.yml"""
        examples_path = self.docs_path / "examples"

        if not examples_path.exists():
            logger.warning("Examples directory not found: %s", examples_path)
            return

        for example_file in examples_path.glob("*.yml"):
            try:
                with open(example_file, encoding='utf-8') as f:
                    example_data = yaml.safe_load(f)
                    if example_data:
                        self.schema["examples"].append(example_data)
                        logger.debug("Loaded example: %s", example_file.name)
            except Exception as e:
                logger.error("Error loading example file %s: %s", example_file, str(e))

    def get_table_names(self) -> List[str]:
        """Get list of all available table names."""
        return list(self.schema["tables"].keys())

    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """Get information about a specific table."""
        return self.schema["tables"].get(table_name, {})
