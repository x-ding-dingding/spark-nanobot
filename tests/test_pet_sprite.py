from pathlib import Path

from PIL import Image, ImageDraw

from nanobot.pet.sprite import split_pet_sprite


def test_split_pet_sprite_writes_expected_state_assets(tmp_path: Path) -> None:
    sheet = tmp_path / "sheet.png"
    image = Image.new("RGBA", (20, 20), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((1, 1, 8, 8), fill=(255, 0, 0, 255))
    draw.rectangle((11, 1, 18, 8), fill=(0, 255, 0, 255))
    draw.rectangle((1, 11, 8, 18), fill=(0, 0, 255, 255))
    draw.rectangle((11, 11, 18, 18), fill=(255, 255, 0, 255))
    image.save(sheet)

    written = split_pet_sprite(
        sheet,
        tmp_path / "out",
        prefix="spark",
        trim=False,
        transparent_background=False,
        output_size=None,
    )

    assert [path.name for path in written] == [
        "spark-idle.png",
        "spark-working.png",
        "spark-warning.png",
        "spark-dragging.png",
    ]
    assert Image.open(written[0]).getpixel((2, 2)) == (255, 0, 0, 255)
    assert Image.open(written[1]).getpixel((2, 2)) == (0, 255, 0, 255)
    assert Image.open(written[2]).getpixel((2, 2)) == (0, 0, 255, 255)
    assert Image.open(written[3]).getpixel((2, 2)) == (255, 255, 0, 255)
