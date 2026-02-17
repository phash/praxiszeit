"""
Generate high-quality PraxisZeit icons for PWA.
Creates a modern medical/time tracking themed icon.
"""
from PIL import Image, ImageDraw, ImageFilter
import math


def create_praxiszeit_icon(size: int) -> Image.Image:
    """Create a polished PraxisZeit icon."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background gradient effect (deep blue)
    # Draw layered circles for depth
    center = size // 2
    r = size // 2

    # Outer gradient background - deep blue
    for i in range(r, 0, -1):
        progress = i / r
        # Gradient from dark navy to primary blue
        blue = int(37 + (59 - 37) * (1 - progress))
        green = int(99 + (130 - 99) * (1 - progress))
        red = int(235 + (220 - 235) * (1 - progress))
        color = (red, green, blue, 255)
        draw.ellipse([center - i, center - i, center + i, center + i], fill=color)

    # Soft inner glow
    for i in range(int(r * 0.85), int(r * 0.6), -1):
        progress = (i - r * 0.6) / (r * 0.25)
        alpha = int(15 * progress)
        draw.ellipse([center - i, center - i, center + i, center + i],
                     fill=(255, 255, 255, alpha))

    # Clock face - white circle
    clock_r = int(r * 0.55)
    draw.ellipse([
        center - clock_r, center - clock_r,
        center + clock_r, center + clock_r
    ], fill=(255, 255, 255, 240))

    # Clock border
    border_width = max(2, size // 48)
    draw.ellipse([
        center - clock_r, center - clock_r,
        center + clock_r, center + clock_r
    ], outline=(255, 255, 255, 255), width=border_width)

    # Clock tick marks
    tick_color = (37, 99, 235)  # primary blue
    for hour in range(12):
        angle = math.radians(hour * 30 - 90)
        if hour % 3 == 0:
            tick_len = clock_r * 0.18
            tick_width = max(2, size // 64)
        else:
            tick_len = clock_r * 0.1
            tick_width = max(1, size // 96)

        outer_x = center + (clock_r - border_width) * math.cos(angle)
        outer_y = center + (clock_r - border_width) * math.sin(angle)
        inner_x = center + (clock_r - border_width - tick_len) * math.cos(angle)
        inner_y = center + (clock_r - border_width - tick_len) * math.sin(angle)

        draw.line([outer_x, outer_y, inner_x, inner_y],
                  fill=tick_color, width=tick_width)

    # Clock hands - pointing to ~10:10 (classic watch position)
    hand_color = (37, 99, 235)
    center_dot_r = max(3, size // 32)

    # Hour hand (pointing ~10 o'clock)
    hour_angle = math.radians(-60)  # 10 o'clock = -60 degrees from 12
    hour_len = clock_r * 0.42
    hour_end_x = center + hour_len * math.cos(hour_angle)
    hour_end_y = center + hour_len * math.sin(hour_angle)
    hand_width = max(2, size // 48)
    draw.line([center, center, hour_end_x, hour_end_y],
              fill=hand_color, width=hand_width + 1)

    # Minute hand (pointing ~2 o'clock)
    min_angle = math.radians(60)  # 2 o'clock
    min_len = clock_r * 0.58
    min_end_x = center + min_len * math.cos(min_angle)
    min_end_y = center + min_len * math.sin(min_angle)
    draw.line([center, center, min_end_x, min_end_y],
              fill=hand_color, width=hand_width)

    # Second hand (red, pointing ~6:30)
    sec_angle = math.radians(15)
    sec_len = clock_r * 0.62
    sec_end_x = center + sec_len * math.cos(sec_angle)
    sec_end_y = center + sec_len * math.sin(sec_angle)
    draw.line([center, center, sec_end_x, sec_end_y],
              fill=(239, 68, 68), width=max(1, size // 96))

    # Center dot
    draw.ellipse([
        center - center_dot_r, center - center_dot_r,
        center + center_dot_r, center + center_dot_r
    ], fill=(37, 99, 235))

    # Small "P" letter or medical cross in top-left of clock
    # Medical cross (small, in top area of clock)
    cross_size = int(clock_r * 0.18)
    cross_x = center - clock_r * 0.35
    cross_y = center - clock_r * 0.55
    cross_color = (220, 38, 38, 200)  # red cross
    cross_thickness = max(2, cross_size // 3)

    # Vertical bar
    draw.rectangle([
        cross_x - cross_thickness // 2, cross_y - cross_size,
        cross_x + cross_thickness // 2, cross_y + cross_size
    ], fill=cross_color)
    # Horizontal bar
    draw.rectangle([
        cross_x - cross_size, cross_y - cross_thickness // 2,
        cross_x + cross_size, cross_y + cross_thickness // 2
    ], fill=cross_color)

    # Apply slight anti-aliasing by resizing down if generating large
    if size > 192:
        img = img.resize((size, size), Image.LANCZOS)

    return img


def main():
    print("Generating PraxisZeit icons...")

    for icon_size in [192, 512]:
        icon = create_praxiszeit_icon(icon_size)
        filename = f"frontend/public/icon-{icon_size}.png"
        icon.save(filename, "PNG", optimize=True)
        print(f"  ✓ Generated {filename} ({icon_size}x{icon_size})")

    # Also generate favicon sizes
    for favicon_size in [32, 64, 180]:
        icon = create_praxiszeit_icon(favicon_size * 2)  # 2x for quality
        icon = icon.resize((favicon_size, favicon_size), Image.LANCZOS)
        if favicon_size == 180:
            filename = f"frontend/public/apple-touch-icon.png"
        else:
            filename = f"frontend/public/favicon-{favicon_size}x{favicon_size}.png"
        icon.save(filename, "PNG", optimize=True)
        print(f"  ✓ Generated {filename}")

    print("Done!")


if __name__ == "__main__":
    main()
