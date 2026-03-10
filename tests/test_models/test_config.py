"""Tests for configuration data models."""

import yaml

from src.models.config import (
    ArxivConfig,
    HackerNewsConfig,
    RSSConfig,
    RSSFeedConfig,
    RedditConfig,
    SourceConfig,
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


class TestRSSFeedConfig:
    def test_create(self):
        feed = RSSFeedConfig(
            name="Test Feed",
            url="https://example.com/rss",
            category="industry",
        )
        assert feed.name == "Test Feed"
        assert feed.category == "industry"

    def test_default_category(self):
        feed = RSSFeedConfig(name="Test", url="https://example.com")
        assert feed.category == "news"


class TestRedditConfig:
    def test_defaults(self):
        config = RedditConfig()
        assert "MachineLearning" in config.subreddits
        assert config.sort == "hot"
        assert config.limit == 25


class TestHackerNewsConfig:
    def test_defaults(self):
        config = HackerNewsConfig()
        assert config.min_score == 50
        assert config.max_items == 30
        assert "AI" in config.keywords


class TestSourceConfig:
    def test_defaults(self):
        config = SourceConfig()
        assert isinstance(config.arxiv, ArxivConfig)
        assert isinstance(config.rss, RSSConfig)
        assert isinstance(config.reddit, RedditConfig)
        assert isinstance(config.hackernews, HackerNewsConfig)

    def test_from_yaml_dict(self):
        yaml_data = {
            "arxiv": {
                "categories": ["cs.AI", "cs.CL"],
                "max_results_per_category": 20,
            },
            "rss": {
                "feeds": [
                    {"name": "Blog", "url": "https://example.com/feed", "category": "industry"},
                ],
            },
            "reddit": {
                "subreddits": ["MachineLearning"],
                "sort": "new",
                "limit": 10,
            },
            "hackernews": {
                "min_score": 100,
                "max_items": 20,
            },
        }
        config = SourceConfig.model_validate(yaml_data)
        assert config.arxiv.max_results_per_category == 20
        assert len(config.rss.feeds) == 1
        assert config.rss.feeds[0].name == "Blog"
        assert config.reddit.sort == "new"
        assert config.hackernews.min_score == 100

    def test_partial_yaml(self):
        """Config should use defaults for missing sections."""
        config = SourceConfig.model_validate({"arxiv": {"categories": ["cs.AI"]}})
        assert config.arxiv.categories == ["cs.AI"]
        assert config.reddit.subreddits == ["MachineLearning", "LocalLLaMA"]

    def test_yaml_roundtrip(self):
        yaml_str = """
arxiv:
  categories: [cs.AI]
  max_results_per_category: 10
reddit:
  subreddits: [test]
  limit: 5
"""
        raw = yaml.safe_load(yaml_str)
        config = SourceConfig.model_validate(raw)
        assert config.arxiv.categories == ["cs.AI"]
        assert config.reddit.subreddits == ["test"]
