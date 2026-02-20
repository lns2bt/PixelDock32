"""Quick regression check for text glyph availability on the 8x32 renderer."""

from app.services.rendering import render_text_with_colors


def lit_pixels(text: str, font_size: str = "small") -> int:
    frame, _ = render_text_with_colors(text, font_size=font_size)
    return sum(sum(row) for row in frame)


def main() -> None:
    # Regressions seen in production preview involved missing letters in words.
    # Check a broad set of letters that commonly appear in module content.
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for ch in letters:
        pixels_small = lit_pixels(ch, "small")
        pixels_normal = lit_pixels(ch, "normal")
        assert pixels_small > 0, f"missing small glyph for {ch}"
        assert pixels_normal > 0, f"missing normal glyph for {ch}"

    # Ensure known problematic samples still render with enough pixels.
    assert lit_pixels("PIXEL", "small") > 20
    assert lit_pixels("STATUS", "small") > 20
    assert lit_pixels("H75%", "small") > 10
    assert lit_pixels("H75%", "normal") > 20

    print("glyph-regression-ok")


if __name__ == "__main__":
    main()
