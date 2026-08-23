"""Built-in challenge/profile bindings for the narrow P0-A slice.

The wizard and non-interactive experiment parser use this same registry.  A
scenario pack is evaluator-owned configuration derived from the selected
challenge and execution track; it is persisted for reproducibility but is not
an independent basic-wizard choice.
"""

from __future__ import annotations

from dataclasses import dataclass


class ChallengeProfileError(ValueError):
    """No compatible built-in challenge/profile binding exists."""


@dataclass(frozen=True, slots=True)
class ChallengeProfile:
    challenge_id: str
    track: str
    scenario_pack: str


_PROFILES = {
    ("busy-intersection/v1", "cloud-subscription"): ChallengeProfile(
        "busy-intersection/v1",
        "cloud-subscription",
        "traffic-intersection-p0a",
    ),
    ("busy-intersection/v1", "local"): ChallengeProfile(
        "busy-intersection/v1",
        "local",
        "traffic-intersection-p0a",
    ),
}


def challenge_profile(challenge_id: str, track: str) -> ChallengeProfile:
    try:
        return _PROFILES[(challenge_id, track)]
    except KeyError as exc:
        raise ChallengeProfileError(
            f"no scenario profile is registered for challenge {challenge_id!r} "
            f"on track {track!r}"
        ) from exc


def scenario_pack_for(challenge_id: str, track: str) -> str:
    return challenge_profile(challenge_id, track).scenario_pack


def challenge_ids_for(track: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            profile.challenge_id
            for profile in _PROFILES.values()
            if profile.track == track
        )
    )


__all__ = [
    "ChallengeProfile",
    "ChallengeProfileError",
    "challenge_ids_for",
    "challenge_profile",
    "scenario_pack_for",
]
