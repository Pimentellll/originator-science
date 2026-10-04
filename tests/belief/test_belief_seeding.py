import numpy as np

from mirage.belief.seeding import belief_stream_seed


def test_belief_stream_seed_separates_belief_and_episode_rngs():
    for episode_seed in range(50):
        belief_seed = belief_stream_seed(episode_seed)
        assert belief_seed != episode_seed
        assert (
            np.random.default_rng([belief_seed, 0]).random()
            != np.random.default_rng(episode_seed).random()
        )
