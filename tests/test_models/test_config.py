"""Tests for configuration data models."""

import yaml

from src.models.config import (
    ArxivConfig,
    BilibiliConfig,
    BilibiliUserConfig,
    GitHubTrendingConfig,
    HackerNewsConfig,
    ProductHuntConfig,
    SemanticScholarConfig,
    SourceConfig,
    TavilyConfig,
    TavilySearchQuery,
    YouTubeChannelConfig,
    YouTubeConfig,
)


class TestArxivConfig:
    def test_defaults(self):
        config = ArxivConfig()
        assert "cs.AI" in config.categories
        assert config.max_results_per_category == 50

    def test_custom(self):
        config = ArxivConfig(categories=["cs.AI"], max_results_per_category=10)
        assert len(config.categories) == 1
        assert config.max_results_per_category == 10


class TestHackerNewsConfig:
    def test_defaults(self):
        config = HackerNewsConfig()
        assert config.min_score == 50
        assert config.max_items == 30
        assert "AI" in config.keywords


class TestYouTubeConfig:
    def test_defaults(self):
        config = YouTubeConfig()
        assert config.channels == []
        assert config.max_results_per_channel == 5

    def test_with_channels(self):
        config = YouTubeConfig(
            channels=[YouTubeChannelConfig(name="Test", channel_id="UC123")],
            max_results_per_channel=3,
        )
        assert len(config.channels) == 1
        assert config.channels[0].name == "Test"


class TestBilibiliConfig:
    def test_defaults(self):
        config = BilibiliConfig()
        assert config.users == []
        assert config.max_results_per_user == 5

    def test_with_users(self):
        config = BilibiliConfig(
            users=[BilibiliUserConfig(name="UP", uid=12345)],
        )
        assert config.users[0].uid == 12345


class TestSemanticScholarConfig:
    def test_defaults(self):
        config = SemanticScholarConfig()
        assert len(config.topics) >= 1
        assert config.max_results == 50


class TestGitHubTrendingConfig:
    def test_defaults(self):
        config = GitHubTrendingConfig()
        assert "python" in config.languages
        assert config.since == "daily"
        assert config.max_items == 30


class TestProductHuntConfig:
    def test_defaults(self):
        config = ProductHuntConfig()
        assert "artificial-intelligence" in config.topics
        assert config.max_items == 20


class TestTavilyConfig:
    def test_defaults(self):
        config = TavilyConfig()
        assert config.searches == []
        assert config.max_results_per_search == 5
        assert config.search_depth == "basic"

    def test_with_searches(self):
        config = TavilyConfig(
            searches=[TavilySearchQuery(name="Test", query="site:test.com")],
        )
        assert len(config.searches) == 1
        assert config.searches[0].query == "site:test.com"


class TestSourceConfig:
    def test_defaults(self):
        config = SourceConfig()
        assert isinstance(config.arxiv, ArxivConfig)
        assert isinstance(config.hackernews, HackerNewsConfig)
        assert isinstance(config.youtube, YouTubeConfig)
        assert isinstance(config.bilibili, BilibiliConfig)
        assert isinstance(config.semantic_scholar, SemanticScholarConfig)
        assert isinstance(config.github_trending, GitHubTrendingConfig)
        assert isinstance(config.product_hunt, ProductHuntConfig)
        assert isinstance(config.tavily, TavilyConfig)

    def test_from_yaml_dict(self):
        yaml_data = {
            "arxiv": {
                "categories": ["cs.AI", "cs.CL"],
                "max_results_per_category": 20,
            },
            "youtube": {
                "channels": [
                    {"name": "Test", "channel_id": "UC123"},
                ],
                "max_results_per_channel": 3,
            },
            "hackernews": {
                "min_score": 100,
                "max_items": 20,
            },
            "tavily": {
                "searches": [
                    {"name": "OpenAI", "query": "site:openai.com/blog"},
                ],
            },
        }
        config = SourceConfig.model_validate(yaml_data)
        assert config.arxiv.max_results_per_category == 20
        assert len(config.youtube.channels) == 1
        assert config.youtube.channels[0].name == "Test"
        assert config.hackernews.min_score == 100
        assert len(config.tavily.searches) == 1

    def test_partial_yaml(self):
        """Config should use defaults for missing sections."""
        config = SourceConfig.model_validate({"arxiv": {"categories": ["cs.AI"]}})
        assert config.arxiv.categories == ["cs.AI"]
        assert config.hackernews.min_score == 50

    def test_yaml_roundtrip(self):
        yaml_str = """
arxiv:
  categories: [cs.AI]
  max_results_per_category: 10
github_trending:
  languages: [python]
  max_items: 5
"""
        raw = yaml.safe_load(yaml_str)
        config = SourceConfig.model_validate(raw)
        assert config.arxiv.categories == ["cs.AI"]
        assert config.github_trending.languages == ["python"]
