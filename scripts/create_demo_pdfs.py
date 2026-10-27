"""Helper script to generate clean, high-quality demo PDFs with tables and numbers for Tier A demo corpus."""

from pathlib import Path

import pymupdf


def create_acme_report_pdf(output_path: Path) -> None:
    doc = pymupdf.open()
    doc.set_metadata(
        {
            "title": "Acme Corporation Annual Financial Report FY2025",
            "author": "Acme Investor Relations",
            "subject": "Annual Report and Consolidated Financial Statements",
        }
    )

    # Page 1: Executive Summary & Overview
    p1 = doc.new_page(width=612, height=792)  # Standard Letter
    p1.insert_text(
        (50, 60), "Acme Corporation Annual Financial Report FY2025", fontsize=18, fontname="helv"
    )
    p1.insert_text((50, 100), "Executive Summary", fontsize=15, fontname="helv")
    p1.insert_text(
        (50, 130),
        "Acme Corporation recorded record consolidated revenue of $120 million in FY2025,\n"
        "representing an increase of 22% year-over-year. Growth was primarily driven by strong\n"
        "adoption of enterprise cloud services and strategic expansions across EMEA and APAC markets.",
        fontsize=11,
        fontname="helv",
    )
    p1.insert_text((50, 200), "Operating Efficiency & Cost Controls", fontsize=13, fontname="helv")
    p1.insert_text(
        (50, 230),
        "Operating expenses decreased by 8% due to automated processing pipelines, workflow optimization,\n"
        "and disciplined vendor management. Operating income reached $34.5 million with an operating\n"
        "margin of 28.75%.",
        fontsize=11,
        fontname="helv",
    )
    p1.insert_text((50, 300), "Research and Development Initiatives", fontsize=13, fontname="helv")
    p1.insert_text(
        (50, 330),
        "R&D expenditures were $18 million in FY2025, focused on next-generation retrieval architectures,\n"
        "AI provenance tracking, and zero-trust key management systems.",
        fontsize=11,
        fontname="helv",
    )

    # Page 2: Financial Performance & Balance Sheet Table
    p2 = doc.new_page(width=612, height=792)
    p2.insert_text(
        (50, 60), "Financial Performance & Segment Breakdown", fontsize=15, fontname="helv"
    )
    p2.insert_text(
        (50, 90),
        "Revenue by business segment in FY2025 was distributed as follows:\n"
        "- Enterprise Cloud: $75,000,000 (62% of total revenue)\n"
        "- Professional Services: $30,000,000 (25% of total revenue)\n"
        "- Licensing & Support: $15,000,000 (13% of total revenue)",
        fontsize=11,
        fontname="helv",
    )
    p2.insert_text((50, 180), "Balance Sheet & Capital Structure", fontsize=13, fontname="helv")
    p2.insert_text(
        (50, 210),
        "Total consolidated assets stood at $185 million at fiscal year-end, with cash reserves\n"
        "of $42 million. The debt-to-equity ratio was maintained conservatively at 0.42.\n"
        "Working capital improved by 14% to $28.6 million.",
        fontsize=11,
        fontname="helv",
    )
    p2.insert_text((50, 290), "Auditor Opinion & Compliance", fontsize=13, fontname="helv")
    p2.insert_text(
        (50, 320),
        "Independent auditors issued an unqualified audit opinion confirming that financial\n"
        "statements present fairly, in all material respects, the financial position of Acme Corporation.",
        fontsize=11,
        fontname="helv",
    )

    doc.save(str(output_path))
    doc.close()


def create_constitution_pdf(output_path: Path) -> None:
    doc = pymupdf.open()
    doc.set_metadata(
        {
            "title": "The Constitution of the United States and the Bill of Rights",
            "author": "Constitutional Convention",
            "subject": "Foundational Legal Document of the United States",
        }
    )

    # Page 1: Preamble & Article I
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((50, 60), "The Constitution of the United States", fontsize=18, fontname="helv")
    p1.insert_text((50, 100), "Preamble", fontsize=15, fontname="helv")
    p1.insert_text(
        (50, 130),
        "We the People of the United States, in Order to form a more perfect Union, establish Justice,\n"
        "insure domestic Tranquility, provide for the common defence, promote the general Welfare,\n"
        "and secure the Blessings of Liberty to ourselves and our Posterity, do ordain and establish\n"
        "this Constitution for the United States of America.",
        fontsize=11,
        fontname="helv",
    )
    p1.insert_text((50, 220), "Article I: The Legislative Branch", fontsize=14, fontname="helv")
    p1.insert_text(
        (50, 250),
        "Section 1. All legislative Powers herein granted shall be vested in a Congress of the\n"
        "United States, which shall consist of a Senate and House of Representatives.\n\n"
        "Section 2. The House of Representatives shall be composed of Members chosen every second\n"
        "Year by the People of the several States.\n\n"
        "Section 3. The Senate of the United States shall be composed of two Senators from each State,\n"
        "chosen for six Years; and each Senator shall have one Vote.",
        fontsize=11,
        fontname="helv",
    )
    p1.insert_text((50, 360), "Article II: The Executive Branch", fontsize=14, fontname="helv")
    p1.insert_text(
        (50, 390),
        "Section 1. The executive Power shall be vested in a President of the United States of America.\n"
        "He shall hold his Office during the Term of four Years, together with the Vice President.",
        fontsize=11,
        fontname="helv",
    )

    # Page 2: The Bill of Rights
    p2 = doc.new_page(width=612, height=792)
    p2.insert_text(
        (50, 60), "The Bill of Rights - Constitutional Amendments", fontsize=16, fontname="helv"
    )
    p2.insert_text(
        (50, 95),
        "Amendment I (Freedom of Religion, Speech, Press, Assembly)",
        fontsize=13,
        fontname="helv",
    )
    p2.insert_text(
        (50, 120),
        "Congress shall make no law respecting an establishment of religion, or prohibiting the free\n"
        "exercise thereof; or abridging the freedom of speech, or of the press; or the right of the people\n"
        "peaceably to assemble, and to petition the Government for a redress of grievances.",
        fontsize=11,
        fontname="helv",
    )
    p2.insert_text((50, 185), "Amendment II (Right to Bear Arms)", fontsize=13, fontname="helv")
    p2.insert_text(
        (50, 210),
        "A well regulated Militia, being necessary to the security of a free State, the right of the people\n"
        "to keep and bear Arms, shall not be infringed.",
        fontsize=11,
        fontname="helv",
    )
    p2.insert_text((50, 265), "Amendment IV (Search and Seizure)", fontsize=13, fontname="helv")
    p2.insert_text(
        (50, 290),
        "The right of the people to be secure in their persons, houses, papers, and effects, against\n"
        "unreasonable searches and seizures, shall not be violated, and no Warrants shall issue,\n"
        "but upon probable cause, supported by Oath or affirmation.",
        fontsize=11,
        fontname="helv",
    )
    p2.insert_text(
        (50, 360), "Amendment V (Rights in Criminal Cases)", fontsize=13, fontname="helv"
    )
    p2.insert_text(
        (50, 385),
        "No person shall be held to answer for a capital, or otherwise infamous crime, unless on a\n"
        "presentment or indictment of a Grand Jury; nor shall any person be subject for the same\n"
        "offence to be twice put in jeopardy of life or limb; nor shall be compelled in any criminal\n"
        "case to be a witness against himself, nor be deprived of life, liberty, or property, without\n"
        "due process of law; nor shall private property be taken for public use, without just compensation.",
        fontsize=11,
        fontname="helv",
    )

    doc.save(str(output_path))
    doc.close()


if __name__ == "__main__":
    out_dir = Path("demo_corpus")
    create_acme_report_pdf(out_dir / "acme_annual_financial_report_2025.pdf")
    create_constitution_pdf(out_dir / "us_constitution_bill_of_rights.pdf")
    print("Demo PDFs generated successfully!")
