"""Golden evaluation dataset for the Ooredoo DZ semantic search system.

This module defines curated query-document relevance judgments used for
offline evaluation of search quality.  Each entry contains:

    - query: a realistic user query
    - relevant_docs: dict of external_id -> graded relevance
        0 = not relevant, 1 = marginally, 2 = relevant, 3 = highly relevant
    - category: thematic grouping for per-category metric breakdowns

The external_ids must match the md5(url) values produced by the crawler.
For unit tests that don't hit the DB, synthetic external_ids are used.

To add new queries: append to GOLDEN_QUERIES and, if needed, to the
DOCUMENTS corpus.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GoldenQuery:
    query: str
    relevant_docs: dict[str, int]
    category: str = ""


@dataclass
class GoldenDocument:
    external_id: str
    title: str
    content: str
    url: str = ""
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Synthetic document corpus (used by unit / integration tests)
# ---------------------------------------------------------------------------

DOCUMENTS: list[GoldenDocument] = [
    # --- Telecom offers ---
    GoldenDocument(
        external_id="doc_offer_5g",
        title="Ooredoo 5G Offers and Coverage",
        content=(
            "Ooredoo Algeria launches its 5G network in major cities including "
            "Algiers, Oran, and Constantine. The 5G plans start at 2000 DA/month "
            "for 50GB of data with speeds up to 1Gbps. Enterprise 5G packages "
            "include dedicated bandwidth and SLA guarantees. Coverage currently "
            "spans urban areas with expansion planned for 2026."
        ),
        url="https://www.ooredoo.dz/5g-offers",
        metadata={"category": "offers", "language": "en"},
    ),
    GoldenDocument(
        external_id="doc_offer_4g",
        title="Forfaits 4G Ooredoo - Internet Mobile",
        content=(
            "Découvrez les forfaits 4G Ooredoo avec des offres allant de 500 DA "
            "à 5000 DA par mois. Le forfait Haya inclut 20GB de données, appels "
            "illimités vers Ooredoo et 2h d'appels vers tous les réseaux. "
            "Activez votre forfait en envoyant un SMS au 600 ou via l'application "
            "My Ooredoo."
        ),
        url="https://www.ooredoo.dz/forfaits-4g",
        metadata={"category": "offers", "language": "fr"},
    ),
    GoldenDocument(
        external_id="doc_offer_prepaid",
        title="Prepaid Recharge Plans",
        content=(
            "Ooredoo prepaid recharge options: 100 DA gives you 1GB for 24h, "
            "200 DA gives 3GB for 3 days, 500 DA gives 10GB for 7 days. "
            "Dial *600# to check your balance. Auto-recharge available via "
            "Ooredoo app with CIB or EDAHABIA cards."
        ),
        url="https://www.ooredoo.dz/prepaid",
        metadata={"category": "offers", "language": "en"},
    ),
    # --- Billing & Payments ---
    GoldenDocument(
        external_id="doc_billing_pay",
        title="How to Pay Your Ooredoo Bill",
        content=(
            "Pay your Ooredoo bill online via the My Ooredoo app, CIB/EDAHABIA "
            "bank cards, or at any Ooredoo retail store. For postpaid customers, "
            "bills are generated on the 1st of each month. Late payment fees of "
            "50 DA/day apply after 15 days. To view your bill, log in to "
            "selfcare.ooredoo.dz or call 888."
        ),
        url="https://www.ooredoo.dz/pay-bill",
        metadata={"category": "billing", "language": "en"},
    ),
    GoldenDocument(
        external_id="doc_billing_dispute",
        title="Contester une facture Ooredoo",
        content=(
            "Si vous constatez une anomalie sur votre facture Ooredoo, vous "
            "pouvez déposer une réclamation en ligne via selfcare.ooredoo.dz "
            "ou en appelant le 888. Les réclamations sont traitées sous 48h "
            "ouvrables. Joignez une copie de votre facture et décrivez "
            "l'anomalie constatée."
        ),
        url="https://www.ooredoo.dz/reclamation-facture",
        metadata={"category": "billing", "language": "fr"},
    ),
    # --- Technical / Network ---
    GoldenDocument(
        external_id="doc_network_coverage",
        title="Ooredoo Network Coverage Map",
        content=(
            "Check Ooredoo network coverage across Algeria. Our 4G LTE network "
            "covers 48 wilayas with 95% population coverage. 5G is available in "
            "Algiers, Oran, Constantine, and Annaba. Use the interactive coverage "
            "map at ooredoo.dz/coverage to verify signal strength in your area. "
            "Report network issues via the My Ooredoo app."
        ),
        url="https://www.ooredoo.dz/coverage",
        metadata={"category": "network", "language": "en"},
    ),
    GoldenDocument(
        external_id="doc_network_apn",
        title="APN Settings for Ooredoo Internet",
        content=(
            "To configure internet on your phone, use these APN settings: "
            "APN: internet, Username: (leave blank), Password: (leave blank), "
            "MCC: 603, MNC: 01. For Android go to Settings > Network > "
            "Access Point Names. For iPhone go to Settings > Cellular > "
            "Cellular Data Network. Restart your phone after saving."
        ),
        url="https://www.ooredoo.dz/apn-settings",
        metadata={"category": "network", "language": "en"},
    ),
    # --- Customer Service ---
    GoldenDocument(
        external_id="doc_support_contact",
        title="Contact Ooredoo Customer Service",
        content=(
            "Reach Ooredoo customer service 24/7: call 888 (free from Ooredoo), "
            "email support@ooredoo.dz, visit any of our 200+ retail stores, or "
            "chat via WhatsApp at +213 555 000 888. For business customers call "
            "801. Average wait time is under 3 minutes."
        ),
        url="https://www.ooredoo.dz/contact",
        metadata={"category": "support", "language": "en"},
    ),
    GoldenDocument(
        external_id="doc_support_sim",
        title="SIM Card Replacement and Activation",
        content=(
            "Lost or damaged SIM? Visit any Ooredoo store with your national ID "
            "to get a replacement SIM for 200 DA. Your number and balance will be "
            "transferred. eSIM activation is available for compatible devices. "
            "New SIM cards activate within 2 hours of purchase."
        ),
        url="https://www.ooredoo.dz/sim-replacement",
        metadata={"category": "support", "language": "en"},
    ),
    # --- Roaming ---
    GoldenDocument(
        external_id="doc_roaming",
        title="International Roaming with Ooredoo",
        content=(
            "Ooredoo international roaming is available in 150+ countries. "
            "Activate roaming by dialing *600*1# before travel. Data roaming "
            "starts at 500 DA/day for 200MB. Roaming packages for Tunisia and "
            "Morocco start at 1000 DA/week for 1GB. Incoming calls while roaming "
            "cost 30 DA/minute."
        ),
        url="https://www.ooredoo.dz/roaming",
        metadata={"category": "roaming", "language": "en"},
    ),
    # --- Irrelevant (for negative testing) ---
    GoldenDocument(
        external_id="doc_careers",
        title="Ooredoo Careers and Job Openings",
        content=(
            "Join the Ooredoo team! We are hiring software engineers, network "
            "technicians, and customer service agents across Algeria. Apply at "
            "careers.ooredoo.dz. Benefits include health insurance, performance "
            "bonuses, and training programs."
        ),
        url="https://www.ooredoo.dz/careers",
        metadata={"category": "corporate", "language": "en"},
    ),
    GoldenDocument(
        external_id="doc_csr",
        title="Ooredoo Corporate Social Responsibility",
        content=(
            "Ooredoo Algeria is committed to community development through "
            "digital literacy programs, school connectivity projects, and "
            "environmental sustainability initiatives. In 2025 we planted "
            "10,000 trees and connected 500 rural schools."
        ),
        url="https://www.ooredoo.dz/csr",
        metadata={"category": "corporate", "language": "en"},
    ),
]


# ---------------------------------------------------------------------------
# Golden queries with graded relevance judgments
# ---------------------------------------------------------------------------

GOLDEN_QUERIES: list[GoldenQuery] = [
    # Q1: Exact intent — user wants 5G plans
    GoldenQuery(
        query="Ooredoo 5G offers and prices",
        relevant_docs={
            "doc_offer_5g": 3,       # perfect match
            "doc_network_coverage": 1,  # mentions 5G availability
        },
        category="offers",
    ),
    # Q2: French language query
    GoldenQuery(
        query="forfaits internet mobile Ooredoo",
        relevant_docs={
            "doc_offer_4g": 3,        # direct match (French)
            "doc_offer_5g": 2,        # also an internet offer
            "doc_offer_prepaid": 2,   # also internet
        },
        category="offers",
    ),
    # Q3: Billing question
    GoldenQuery(
        query="how to pay my Ooredoo bill online",
        relevant_docs={
            "doc_billing_pay": 3,
            "doc_billing_dispute": 1,  # related to billing
        },
        category="billing",
    ),
    # Q4: Technical support — APN setup
    GoldenQuery(
        query="configure internet settings on my phone",
        relevant_docs={
            "doc_network_apn": 3,
        },
        category="network",
    ),
    # Q5: Natural language / conversational
    GoldenQuery(
        query="I lost my SIM card what should I do",
        relevant_docs={
            "doc_support_sim": 3,
            "doc_support_contact": 1,  # can help via support
        },
        category="support",
    ),
    # Q6: Roaming information
    GoldenQuery(
        query="roaming data packages for travel to Tunisia",
        relevant_docs={
            "doc_roaming": 3,
        },
        category="roaming",
    ),
    # Q7: Semantic reformulation — no exact keywords
    GoldenQuery(
        query="how much data do I get for 200 dinars",
        relevant_docs={
            "doc_offer_prepaid": 3,    # mentions 200 DA -> 3GB
            "doc_offer_4g": 1,         # has pricing but not 200DA
        },
        category="offers",
    ),
    # Q8: Coverage check
    GoldenQuery(
        query="does Ooredoo have network coverage in my wilaya",
        relevant_docs={
            "doc_network_coverage": 3,
        },
        category="network",
    ),
    # Q9: Multilingual intent — Arabic transliterated
    GoldenQuery(
        query="recharge Ooredoo balance edahabia",
        relevant_docs={
            "doc_offer_prepaid": 3,    # mentions EDAHABIA
            "doc_billing_pay": 2,      # mentions EDAHABIA payment
        },
        category="billing",
    ),
    # Q10: Contesting a bill (French)
    GoldenQuery(
        query="réclamation facture Ooredoo",
        relevant_docs={
            "doc_billing_dispute": 3,
            "doc_billing_pay": 1,
        },
        category="billing",
    ),
    # Q11: Vague query — should still surface something useful
    GoldenQuery(
        query="Ooredoo Algeria",
        relevant_docs={
            # Many docs are relevant, but 5G + coverage are most representative
            "doc_offer_5g": 2,
            "doc_network_coverage": 2,
            "doc_support_contact": 1,
        },
        category="general",
    ),
    # Q12: Customer service contact
    GoldenQuery(
        query="Ooredoo customer service phone number",
        relevant_docs={
            "doc_support_contact": 3,
        },
        category="support",
    ),
    # Q13: eSIM query
    GoldenQuery(
        query="does Ooredoo support eSIM",
        relevant_docs={
            "doc_support_sim": 3,
        },
        category="support",
    ),
    # Q14: Negative test — query about something not in corpus
    GoldenQuery(
        query="Ooredoo stock price and financial results",
        relevant_docs={},  # nothing relevant in corpus
        category="negative",
    ),
    # Q15: Synonym / paraphrase test
    GoldenQuery(
        query="cheapest mobile data plan",
        relevant_docs={
            "doc_offer_prepaid": 3,    # 100 DA is cheapest
            "doc_offer_4g": 2,
            "doc_offer_5g": 1,
        },
        category="offers",
    ),
]


def get_all_relevant_ids(query: GoldenQuery) -> set[str]:
    """Return external_ids with relevance >= 1 (binary relevant)."""
    return {doc_id for doc_id, grade in query.relevant_docs.items() if grade >= 1}
