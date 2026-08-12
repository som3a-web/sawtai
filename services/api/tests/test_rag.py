from sawtai.rag.service import structure_chunks


def test_structure_chunks_preserves_headings_and_size_limit() -> None:
    content = "# السياسة العامة\n\n" + " ".join(f"كلمة{i}" for i in range(190)) + "\n\n## الاستثناءات\n\nنص الاستثناء"

    chunks = structure_chunks(content)

    assert len(chunks) == 3
    assert chunks[0][0] == "السياسة العامة"
    assert len(chunks[0][1].split()) == 180
    assert chunks[1][0] == "السياسة العامة"
    assert chunks[2] == ("الاستثناءات", "نص الاستثناء")
