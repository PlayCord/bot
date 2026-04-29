-- Migration 3.0.1
-- Relax games.rating_config key validation to match runtime game registration payload.

ALTER TABLE IF EXISTS games
    DROP CONSTRAINT IF EXISTS chk_game_rating_config_keys;

ALTER TABLE IF EXISTS games
    ADD CONSTRAINT chk_game_rating_config_keys CHECK (
        rating_config ? 'sigma' AND
        rating_config ? 'beta' AND
        rating_config ? 'tau' AND
        rating_config ? 'draw'
        );
