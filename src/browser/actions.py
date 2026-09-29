import random
import time

class HumanActions:
    """
    Simulates human-like interactions to prevent LinkedIn bot detection.
    Adds random delays, smooth scrolling, and mouse movements.
    """

    @staticmethod
    def random_wait(min_seconds: float = 2.0, max_seconds: float = 5.0):
        """Pause execution for a random duration to mimic human pacing."""
        duration = random.uniform(min_seconds, max_seconds)
        time.sleep(duration)

    @staticmethod
    def reading_pause(text_len: int = 0, min_seconds: float = 1.6, max_seconds: float = 3.6):
        """
        Pause for a realistic human reading interval.
        Longer texts generate slightly longer contemplation intervals.
        """
        bonus = min(2.0, text_len / 400.0) if text_len > 0 else 0
        duration = random.uniform(min_seconds, max_seconds) + bonus
        time.sleep(duration)

    @staticmethod
    def smooth_scroll(page, scroll_steps: int = 5):
        """Alias for human_scroll with default steps."""
        HumanActions.human_scroll(page, min_steps=max(2, scroll_steps - 1), max_steps=scroll_steps + 2)

    @staticmethod
    def human_scroll(page, min_steps: int = 3, max_steps: int = 6):
        """
        Scrolls down the page in small, natural human increments with:
        - Variable step distances (160px - 380px)
        - Subtle mouse cursor wandering
        - 25% chance of an occasional slight upward backtrack (60px - 140px)
        """
        try:
            viewport = page.viewport_size or {"width": 1280, "height": 800}
            center_x = viewport["width"] // 2 + random.randint(-150, 150)
            center_y = viewport["height"] // 2 + random.randint(-100, 100)
            page.mouse.move(center_x, center_y)
        except Exception:
            pass

        steps = random.randint(min_steps, max_steps)
        for i in range(steps):
            # 25% chance to slightly scroll UP (backtrack) to simulate re-reading
            if i > 0 and random.random() < 0.25:
                backtrack_distance = -random.randint(60, 140)
                try:
                    page.mouse.wheel(0, backtrack_distance)
                    page.evaluate(f"window.scrollBy(0, {backtrack_distance})")
                except Exception:
                    pass
                time.sleep(random.uniform(0.5, 1.1))

            scroll_distance = random.randint(180, 360)

            # 1. Native mouse wheel event
            try:
                page.mouse.wheel(0, scroll_distance)
            except Exception:
                pass

            # 2. Scroll window + nested containers
            try:
                page.evaluate(f"""() => {{
                    window.scrollBy(0, {scroll_distance});
                    const selectors = [
                        '.scaffold-layout__main',
                        '.search-results-container',
                        'div[data-view-name]',
                        'main',
                        '.jobs-search-results-list',
                        'div.feed-shared-update-v2'
                    ];
                    selectors.forEach(sel => {{
                        document.querySelectorAll(sel).forEach(el => {{
                            try {{ el.scrollBy(0, {scroll_distance}); }} catch(e) {{}}
                        }});
                    }});
                }}""")
            except Exception:
                pass

            # 3. Occasional keyboard PageDown for deep pagination
            if random.random() < 0.35:
                try:
                    page.keyboard.press("PageDown")
                except Exception:
                    pass

            time.sleep(random.uniform(0.7, 1.5))

    @staticmethod
    def scroll_element_into_view(page, element):
        """Scrolls a specific element into view smoothly."""
        try:
            element.scroll_into_view_if_needed()
            time.sleep(random.uniform(0.6, 1.3))
        except Exception:
            pass

    @staticmethod
    def subtle_mouse_jitter(page):
        """Subtly wander the mouse to simulate natural human hesitation."""
        try:
            viewport = page.viewport_size or {"width": 1280, "height": 800}
            target_x = random.randint(200, viewport["width"] - 200)
            target_y = random.randint(150, viewport["height"] - 150)
            page.mouse.move(target_x, target_y)
            time.sleep(random.uniform(0.3, 0.7))
        except Exception:
            pass

