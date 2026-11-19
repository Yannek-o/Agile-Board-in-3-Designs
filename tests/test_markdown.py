from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.backlog.services import add_comment
from apps.core.markdown import render_markdown
from apps.projects.models import ProjectMembership
from tests.factories import add_member, make_item, make_project, make_user

Access = ProjectMembership.AccessLevel


class MarkdownRenderingTests(SimpleTestCase):
    def test_inline_formatting(self):
        html = render_markdown("**fett**, *kursiv*, ~~weg~~ und `code`")
        self.assertIn("<strong>fett</strong>", html)
        self.assertIn("<em>kursiv</em>", html)
        self.assertIn("<del>weg</del>", html)
        self.assertIn("<code>code</code>", html)

    def test_headings_lists_and_quotes(self):
        html = render_markdown(
            "# Titel\n\n- eins\n- zwei\n\n1. erst\n2. dann\n\n> Zitat"
        )
        self.assertIn("<h3>Titel</h3>", html)
        self.assertIn("<ul><li>eins</li><li>zwei</li></ul>", html)
        self.assertIn("<ol><li>erst</li><li>dann</li></ol>", html)
        self.assertIn("<blockquote>Zitat</blockquote>", html)

    def test_task_list(self):
        html = render_markdown("- [x] fertig\n- [ ] offen")
        self.assertIn('<input type="checkbox" disabled checked> fertig', html)
        self.assertIn('<input type="checkbox" disabled> offen', html)

    def test_code_block_keeps_content_literal(self):
        html = render_markdown("```\n**nicht fett** <b>\n```")
        self.assertIn("<pre><code>**nicht fett** &lt;b&gt;</code></pre>", html)

    def test_links_only_for_http(self):
        html = render_markdown("[Doku](https://example.com/a?b=1&c=2)")
        self.assertIn(
            '<a href="https://example.com/a?b=1&amp;c=2" target="_blank" '
            'rel="noopener noreferrer">Doku</a>',
            html,
        )
        self.assertNotIn("href", render_markdown("[x](javascript:alert(1))"))

    def test_bare_urls_become_links(self):
        html = render_markdown("Siehe https://example.com")
        self.assertIn('href="https://example.com"', html)

    def test_html_is_escaped(self):
        html = render_markdown('<script>alert(1)</script> <img src=x onerror="y">')
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;", html)

    def test_paragraphs_and_line_breaks(self):
        html = render_markdown("Zeile 1\nZeile 2\n\nAbsatz 2")
        self.assertIn("<p>Zeile 1<br>Zeile 2</p>", html)
        self.assertIn("<p>Absatz 2</p>", html)

    def test_mentions_are_highlighted_outside_code(self):
        html = render_markdown("Hallo @anna und `@code`", mentions=True)
        self.assertIn('<span class="mention">@anna</span>', html)
        self.assertIn("<code>@code</code>", html)

    def test_empty_text(self):
        self.assertEqual(render_markdown(""), "")


class MarkdownInPagesTests(TestCase):
    def test_description_and_comments_are_rendered(self):
        project = make_project("MD")
        user = make_user(username="anna")
        add_member(project, user, access_level=Access.EDIT)
        item = make_item(project, description="**Wichtig**\n- Punkt")
        add_comment(item, user, "Bitte `pytest` laufen lassen, @anna")
        self.client.force_login(user)
        response = self.client.get(reverse("backlog:detail", args=["MD", item.number]))
        self.assertContains(response, "<strong>Wichtig</strong>", html=False)
        self.assertContains(response, "<code>pytest</code>", html=False)
        self.assertContains(response, 'class="mention"')
