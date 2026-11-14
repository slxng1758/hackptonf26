"""Worlds to run. Each preset has a hidden truth, the roles that carry it, and the events each generation lives through.

The truth is only ever shown to the evaluator. The civilization never sees it after generation 0.
"""

PRESETS = {
    "village": {
        "title": "The Well",
        "truth_short": "Dirty water made people sick. Boiling it stopped the sickness.",
        "truth": (
            "The village well water became dirty and made people sick. A resident boiled the water before drinking it, "
            "and the people who boiled their water stopped getting sick. Boiling the water is what protected them. "
            "The practice that matters: boil drinking water before drinking it, especially when the water may be dirty or cloudy."
        ),
        "genesis": (
            "This spring the well water turned cloudy and many people fell ill with fever and stomach pains. "
            "Mira the herbalist boiled her family's water in a pot before drinking it, and her family stayed well. "
            "Others who boiled their water also stopped getting sick. Those who drank straight from the well kept falling ill."
        ),
        "people": "a small farming village with no writing tradition beyond simple notes",
        "roles": {
            "physician": "You are the village healer. You care about what actually keeps people alive. Preserve practical knowledge of what works and why, in plain words.",
            "storyteller": "You are the storyteller. You make the past memorable so children remember it. You favor vivid stories, heroes and meaning over dry detail.",
            "ruler": "You are the chief. You turn important matters into rules people must follow, with clear duties and punishments. You care about order and authority.",
            "skeptic": "You are the village skeptic. You look for contradictions, test claims against what you see, and say plainly when a custom seems pointless or wrong.",
        },
        "events": [
            "A dry summer. The well runs low and firewood is scarce.",
            "Sickness breaks out in a neighboring village that drinks from the river.",
            "A traveling merchant mocks the village's water custom as superstition.",
            "A flood muddies every water source for a month.",
            "A new chief proposes cutting old customs to save firewood for winter.",
            "Children fall ill after a harvest festival where people drank straight from the stream.",
            "A new, clear spring is found in the hills. Some say the old customs no longer apply.",
            "A long peaceful decade. Nobody has fallen sick from water in living memory.",
        ],
    },
    "company": {
        "title": "The Runbook",
        "truth_short": "Stale cache from the old schema broke sessions. Flushing it fixed them.",
        "truth": (
            "One Friday a deploy went out while a stale cache entry from the old schema was still in Redis. "
            "The new code read the stale entry and corrupted user sessions. An engineer flushed the Redis "
            "cache before redeploying and the problem went away. The real cause: stale cache entries written "
            "by the previous schema version. The practice that matters: invalidate caches whose schema changed "
            "in a deploy. Flushing everything is only a blunt workaround, and it is only needed when the schema changes."
        ),
        "genesis": (
            "Incident #412: after Friday's deploy, users were logged out and some saw other users' carts. "
            "Priya flushed the Redis cache and redeployed, and everything recovered. Postmortem note: the old "
            "code had written session objects in the v1 format, and the new code expected v2."
        ),
        "people": "a 40-person software company where people leave and join every few months",
        "roles": {
            "physician": "You are the on-call engineer. You care about what actually prevents outages. Preserve the technical cause and fix precisely.",
            "storyteller": "You are the engineer who gives onboarding talks. You turn incidents into memorable war stories new hires will remember.",
            "ruler": "You are the engineering manager. You turn lessons into mandatory process and checklists that everyone must follow.",
            "skeptic": "You are the skeptical SRE. You question rituals, ask for evidence, and push to remove steps nobody can justify.",
        },
        "events": [
            "Quarter-end crunch. Everyone wants deploys to be faster.",
            "A deploy with no schema change takes 40 minutes because of the cache flush. People complain.",
            "Half the team that remembered incident #412 has left.",
            "A new hire asks why we flush Redis before every deploy.",
            "A schema migration ships on a Friday.",
            "Leadership asks to cut 'legacy process' to speed up shipping.",
            "The company switches from Redis to a new cache service.",
            "Two calm years. No session incidents in living memory.",
        ],
    },
}

# Same village, no healer and no skeptic, a priest instead, and only oral memory. The control for "do institutions matter?"
PRESETS["village_oral"] = {
    **PRESETS["village"],
    "title": "The Well, without healers",
    "people": "a small farming village that cannot write; only short sayings, songs and rules passed by mouth survive",
    "roles": {
        "storyteller": PRESETS["village"]["roles"]["storyteller"],
        "ruler": PRESETS["village"]["roles"]["ruler"],
        "priest": "You are the village priest. You explain why things happen in terms of the ancestors, the spirits and the sacred. You keep the rites that protect the village.",
        "elder": "You are the oldest villager. You remember what your grandparents told you, and you pass on the sayings that matter most, simply, as a grandparent would.",
    },
}

# Maximum pressure: one remembered saying, a priest who wants awe, and events that never test the practice directly.
PRESETS["village_myth"] = {
    **PRESETS["village"],
    "title": "The Well, as legend",
    "people": (
        "a village that cannot write. Each generation passes on exactly ONE short saying, chanted at the harvest fire. "
        "Nothing else survives. People value sayings that are beautiful, sacred and easy to chant over sayings that are precise"
    ),
    "roles": {
        "priest": "You are the priest. You explain everything through the ancestors, the spirits and the sacred fire. You want the saying to fill people with awe, and you reshape it so the ancestors get the credit.",
        "bard": "You are the bard. You turn the saying into a short chant with rhythm and images. You happily trade accuracy for beauty, and you add mythic figures.",
        "chief": "You are the chief. You want the saying to command obedience to the old ways and to the chief's family.",
        "child": "You are a child who half-heard the chant. You repeat it the way you remember it, mixing up words and filling gaps with what sounds right.",
    },
    "events": [
        "A great harvest festival. The saying is chanted all night.",
        "A peaceful decade. No one remembers anyone falling sick.",
        "The old priest dies. Her apprentice must recite the saying from memory.",
        "A comet crosses the sky. People look for its meaning in the old saying.",
        "A wedding between two families. The saying is sung as a blessing.",
        "Drought. The village prays at the well.",
        "Strangers arrive and ask what the saying means.",
        "A child is born to the chief. The saying is spoken over the cradle.",
    ],
}

ROLE_ORDER = ["physician", "storyteller", "ruler", "skeptic"]  # default; each preset's own roles take priority
