import unittest
from pathlib import Path

from itau_ri_sanitize.classify import KEEP, REMOVE, REVIEW, classify_text, expand_neighbors
from itau_ri_sanitize.families import family_from_filename, slug_from_filename
from itau_ri_sanitize.lexicon import load_lexicon
from itau_ri_sanitize.paths import lexicon_path, repo_root


LEX = load_lexicon(lexicon_path())

REPORT = """
Independent Auditor's Report on the Consolidated Financial Statement
To the Board of Directors and Stockholders
Itaú Unibanco Holding S.A.
We have audited the accompanying consolidated financial statements.
"""

COUNCIL = """
ATA SUMÁRIA DA REUNIÃO DO CONSELHO FISCAL
Após exame das demonstrações contábeis, e de acordo com o relatório sem ressalvas da
PricewaterhouseCoopers Auditores Independentes, são de opinião que esses documentos refletem a situação.
"""

TOC = """
Sumário
Relatório dos Auditores Independentes ........ 71
Demonstrações Contábeis Completas .......... 73
"""

NOTES = """
NOTAS EXPLICATIVAS ÀS DEMONSTRAÇÕES FINANCEIRAS (Continuação)
O quadro abaixo apresenta a carteira dos ativos financeiros.
"""

CADASTRO = """
Auditores Independentes da Companhia
PricewaterhouseCoopers Auditores Independentes Ltda.
CNPJ 61.562.112/0001-20
"""

SIGNATURE = """
São Paulo, 12 de abril de 2021
PricewaterhouseCoopers Auditores Independentes
CRC 2SP000160/O-5
Emerson Laerte da Silva
"""


class ClassifyTests(unittest.TestCase):
    def test_singular_portuguese_title_beats_committee_mention(self):
        text = """
        a) Comitê de Auditoria Único
        PARECER DOS ATUÁRIOS AUDITORES INDEPENDENTES
        RELATÓRIO DO AUDITOR INDEPENDENTE SOBRE AS DEMONSTRAÇÕES FINANCEIRAS
        Aos Administradores e Acionistas
        Nossa responsabilidade é a de expressar uma opinião.
        """
        decision = classify_text(text, page_index=7, n_pages=9, family="demonstracoes", lexicon=LEX)
        self.assertEqual(decision.action, REMOVE)
        self.assertIn("titulo", decision.reasons)

    def test_report_is_removed(self):
        decision = classify_text(REPORT, page_index=2, n_pages=156, family="demonstracoes", lexicon=LEX)
        self.assertEqual(decision.action, REMOVE)
        self.assertIn("titulo", decision.reasons)
        self.assertIn("verbo_opiniao", decision.reasons)

    def test_council_mention_stays(self):
        decision = classify_text(COUNCIL, page_index=0, n_pages=1, family="conselho_fiscal", lexicon=LEX)
        self.assertEqual(decision.action, KEEP)

    def test_toc_stays(self):
        decision = classify_text(TOC, page_index=1, n_pages=200, family="analise_gerencial", lexicon=LEX)
        self.assertNotEqual(decision.action, REMOVE)

    def test_notes_continuation_is_not_the_report(self):
        decision = classify_text(NOTES, page_index=40, n_pages=216, family="analise_gerencial", lexicon=LEX)
        self.assertEqual(decision.action, KEEP)

    def test_neighbor_notes_are_not_pulled_in(self):
        base = [
            classify_text(REPORT, page_index=0, n_pages=3, family="outros", lexicon=LEX),
            classify_text(NOTES, page_index=1, n_pages=3, family="outros", lexicon=LEX),
            classify_text("Caixa e bancos 10.000", page_index=2, n_pages=3, family="outros", lexicon=LEX),
        ]
        expanded = expand_neighbors(base, [REPORT, NOTES, "Caixa e bancos 10.000"], [False, False, False], LEX)
        self.assertEqual(expanded[1].action, KEEP)
        self.assertEqual(expanded[2].action, KEEP)

    def test_company_accountant_crc_is_not_the_auditor(self):
        text = """
        NOTAS EXPLICATIVAS (Continuação)
        Contador
        Arnaldo Alves dos Santos
        CRC 1SP210058/O-3
        Sede: São Paulo
        """
        decision = classify_text(text, page_index=40, n_pages=90, family="demonstracoes", lexicon=LEX)
        self.assertNotEqual(decision.action, REMOVE)

    def test_signature_page_is_removed(self):
        decision = classify_text(SIGNATURE, page_index=8, n_pages=9, family="demonstracoes", lexicon=LEX)
        self.assertEqual(decision.action, REMOVE)
        self.assertIn("crc", decision.reasons)

    def test_start_of_statements_goes_to_review(self):
        decision = classify_text(
            "Balanço patrimonial\nCaixa 13.967\nAplicações 63.701",
            page_index=3,
            n_pages=156,
            family="demonstracoes",
            lexicon=LEX,
        )
        self.assertEqual(decision.action, REVIEW)
        self.assertIn("zona_inicio", decision.reasons)

    def test_middle_of_statements_stays(self):
        decision = classify_text(
            "Nota 16. Vencimentos contratuais dos ativos e passivos financeiros, "
            "considerando os fluxos nao descontados. Caixa 13.967. Depositos a prazo 34.916. "
            "Aplicacoes interfinanceiras de liquidez 63.701. O quadro seguinte detalha os prazos.",
            page_index=80,
            n_pages=156,
            family="demonstracoes",
            lexicon=LEX,
        )
        self.assertEqual(decision.action, KEEP)

    def test_cadastro_in_reference_form_is_not_deleted(self):
        decision = classify_text(CADASTRO, page_index=1, n_pages=480, family="formulario_referencia", lexicon=LEX)
        self.assertNotEqual(decision.action, REMOVE)

    def test_hash_prefix_does_not_become_a_family(self):
        name = "a1b2c3d4e5f6" * 5 + "20f0" + "_fato_relevante_pagamento.pdf"
        self.assertEqual(len(name.split("_")[0]), 64)
        self.assertEqual(slug_from_filename(name), "fato_relevante_pagamento")
        self.assertEqual(family_from_filename(name), "fato_relevante")

    def test_lexicon_file_is_in_the_repo(self):
        self.assertTrue((repo_root() / "config" / "lexicon.yml").is_file())


if __name__ == "__main__":
    unittest.main()
