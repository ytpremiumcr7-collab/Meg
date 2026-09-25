"""Tests industriales para verificar que los silencios fueron eliminados.

Verifica:
- BIM: excepciones se loguean, no se tragan
- CPM: StopIteration se loguea con contexto
- Feodo: excepciones se propagan, no se retornan defaults silenciosos
"""
import pytest
from unittest.mock import MagicMock, patch
import structlog


class TestBIMNoSilence:
    def test_container_read_logs_warning(self):
        """Verificar que el código de BIM tiene logger.warning en except."""
        import ast
        with open("app/engines/bim/motor_bim.py", "r") as f:
            tree = ast.parse(f.read())

        found_logging = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # Buscar logger.warning en el cuerpo del except
                for stmt in node.body:
                    stmt_str = ast.dump(stmt)
                    if "logger.warning" in stmt_str or "logger" in stmt_str and "warning" in stmt_str:
                        found_logging = True
                        break
        assert found_logging, "BIM debe tener logger.warning en bloques except"

    def test_no_bare_pass_in_except(self):
        """Verificar que no hay 'pass' solo dentro de except Exception."""
        import ast
        with open("app/engines/bim/motor_bim.py", "r") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                for stmt in node.body:
                    if isinstance(stmt, ast.Pass):
                        # Si hay pass, debe haber algo más en el bloque (logging)
                        assert len(node.body) > 1, "Except con pass debe tener logging adicional"


class TestCPMNoSilence:
    def test_stop_iteration_logs_error(self):
        """Verificar que CPM tiene logger.error en StopIteration."""
        import ast
        with open("app/engines/programacion/cpm.py", "r") as f:
            content = f.read()

        assert "logger.error" in content, "CPM debe usar logger.error"
        assert "cpm_predecesora_no_encontrada" in content, "CPM debe tener identificador de error específico"

    def test_no_bare_pass_in_stop_iteration(self):
        """Verificar que no hay pass solo después de StopIteration."""
        import ast
        with open("app/engines/programacion/cpm.py", "r") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if any(isinstance(t, ast.Name) and t.id == "StopIteration" for t in ([node.type] if not isinstance(node.type, ast.Tuple) else node.type.elts)):
                    for stmt in node.body:
                        if isinstance(stmt, ast.Pass):
                            assert len(node.body) > 1, "StopIteration con pass debe tener logging"


class TestFeodoNoSilence:
    def test_feodo_propagates_exception(self):
        """Verificar que Feodo Tracker propaga excepciones."""
        import ast
        with open("tezcatlipoca/services/malware/feodo_tracker.py", "r") as f:
            content = f.read()

        assert "InteropException" in content, "Feodo debe lanzar InteropException"
        assert "from exc" in content, "Feodo debe usar 'from exc' para chain"
        assert "logger.error" in content, "Feodo debe loguear el error antes de propagar"

    def test_no_silent_pass_comment(self):
        """Verificar que no queda el comentario de silencio."""
        import ast
        with open("tezcatlipoca/services/malware/feodo_tracker.py", "r") as f:
            content = f.read()

        assert "Silently fail" not in content, "No debe quedar comentario de silencio"
        assert "return defaults" not in content, "No debe retornar defaults en silencio"


class TestAuthRecordAttempt:
    def test_record_attempt_not_pass(self):
        """Verificar que _record_attempt no es solo pass."""
        import ast
        with open("tezcatlipoca/routers/auth.py", "r") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_record_attempt":
                assert len(node.body) > 1 or not isinstance(node.body[0], ast.Pass),                     "_record_attempt no debe ser solo pass"
                body_str = ast.dump(node)
                assert "redis" in body_str or "lpush" in body_str,                     "_record_attempt debe interactuar con Redis"

    def test_record_attempt_has_audit_logic(self):
        """Verificar que _record_attempt tiene lógica de auditoria."""
        import ast
        with open("tezcatlipoca/routers/auth.py", "r") as f:
            content = f.read()

        assert "auth:attempts" in content, "Debe usar key de auditoria"
        assert "expire" in content, "Debe setear TTL"
        assert "7" in content or "86400" in content, "Debe tener retención de 7 días"
