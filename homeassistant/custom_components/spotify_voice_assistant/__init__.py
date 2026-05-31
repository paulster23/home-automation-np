"""Spotify Voice Assistant Search Integration for Home Assistant."""
import logging
import re
import xml.etree.ElementTree as ET
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

DOMAIN = "spotify_voice_assistant"
VALID_SEARCH_TYPES = {"artist", "album", "track", "playlist", "show", "episode"}

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

# Cache Spotify client to avoid repeated lookups
_spotify_cache = {
    "client": None,
    "entity_id": None,
    "user_playlists": None,
}


def clean_query(query: str, search_type: str) -> str:
    """Remove common command words to improve search accuracy."""
    query = query.lower().strip()

    # Remove "play" from the start of any query
    if query.startswith("play "):
        query = query[5:]

    # Remove type-specific filler words
    if search_type == "artist":
        # Remove "artist" prefix if LLM included it
        query = query.replace("artist ", "").replace(
            "group ", "").replace("band ", "")
    elif search_type == "album":
        # Remove "album" prefix
        query = query.replace("album ", "")
    elif search_type == "track":
        # Remove "song" or "track" prefix
        query = query.replace("song ", "").replace("track ", "")
    elif search_type in ("show", "episode"):
        # Remove "podcast" prefix words
        query = query.replace("podcast ", "").replace("the podcast ", "")

    return " ".join(query.split()).strip()


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Spotify Voice Assistant Search component."""

    async def get_spotify_client():
        """Get Spotify client with caching and validation."""
        if _spotify_cache["client"] is not None:
            if _spotify_cache["entity_id"] in hass.states.async_entity_ids():
                _LOGGER.debug("Using cached Spotify client")
                return _spotify_cache["client"]
            else:
                _LOGGER.info(
                    "Cached Spotify entity no longer exists, invalidating cache")
                _spotify_cache["client"] = None
                _spotify_cache["entity_id"] = None
                _spotify_cache["user_playlists"] = None

        _LOGGER.debug("Cache miss, performing Spotify entity lookup")

        spotify_entity_id = None
        for state in hass.states.async_all("media_player"):
            if "spotify" in state.entity_id.lower():
                spotify_entity_id = state.entity_id
                break

        if not spotify_entity_id:
            _LOGGER.error("No Spotify media player entity found")
            raise LookupError("Spotify not configured")

        entity_component = hass.data.get(
            "entity_components", {}).get("media_player")
        if not entity_component:
            raise LookupError("Media player component not available")

        spotify_entity = None
        for entity in entity_component.entities:
            if entity.entity_id == spotify_entity_id:
                spotify_entity = entity
                break

        if not spotify_entity:
            raise LookupError("Spotify entity not available")

        if not hasattr(spotify_entity, "coordinator"):
            raise AttributeError("Spotify coordinator not available")

        coordinator = spotify_entity.coordinator
        if not hasattr(coordinator, "client"):
            raise AttributeError("Spotify client not available")

        client = coordinator.client
        _spotify_cache["client"] = client
        _spotify_cache["entity_id"] = spotify_entity_id
        _LOGGER.info("Cached Spotify client for entity: %s", spotify_entity_id)

        return client

    async def search_spotify(call: ServiceCall):
        """Search Spotify and return the first result's URI."""
        raw_query = call.data.get("query")
        search_type = call.data.get("type", "artist")

        if not raw_query:
            _LOGGER.error("No query provided to spotify_voice_assistant")
            return {"error": "No query provided"}

        if search_type not in VALID_SEARCH_TYPES:
            return {"error": f"Invalid type. Must be one of: {', '.join(VALID_SEARCH_TYPES)}"}

        # --- UPDATE: Clean the query before sending to Spotify ---
        query = clean_query(raw_query, search_type)
        _LOGGER.info("Searching Spotify (%s) for cleaned query: '%s' (raw: '%s')",
                     search_type, query, raw_query)

        try:
            client = await get_spotify_client()
        except (LookupError, AttributeError) as err:
            _LOGGER.error("Failed to get Spotify client: %s", err)
            return {"error": str(err)}

        try:
            if search_type == "artist":
                results = await client.search(query, ["artist"], limit=10)
                items_list = results.artists
                if items_list and len(items_list) > 0:
                    exact_match = None
                    query_lower = query.lower()
                    for artist in items_list:
                        if hasattr(artist, "name") and artist.name.lower() == query_lower:
                            exact_match = artist
                            break

                    selected_artist = exact_match if exact_match else items_list[0]

                    if not hasattr(selected_artist, "uri"):
                        return {"error": "Invalid artist data from Spotify"}

                    uri = selected_artist.uri
                    name = selected_artist.name
                    match_type = "exact match" if exact_match else "first result"
                    result = {"uri": uri, "name": name, "type": "artist"}
                    _LOGGER.info("✅ SEARCH RESULT (%s): %s",
                                 match_type, result)
                    return result
                else:
                    error_result = {"error": f"No artist found for: {query}"}
                    _LOGGER.error("❌ SEARCH ERROR: %s", error_result)
                    return error_result

            elif search_type == "playlist":
                # Cleaning is already handled by clean_query logic above,
                # but we keep the specific 'playlist' word removal for safety
                query_cleaned = query.lower().replace(
                    "playlist", "").replace("playlists", "").strip()

                # 1. Search User Library
                try:
                    if _spotify_cache["user_playlists"] is None:
                        user_playlists_response = await client.get_playlists_for_current_user()
                        if user_playlists_response and hasattr(user_playlists_response, "items"):
                            _spotify_cache["user_playlists"] = user_playlists_response.items
                        else:
                            _spotify_cache["user_playlists"] = []

                    user_playlists = _spotify_cache["user_playlists"]

                    # Exact match in library
                    for playlist in user_playlists:
                        if hasattr(playlist, "name") and playlist.name.lower() == query_cleaned:
                            result = {"uri": playlist.uri,
                                      "name": playlist.name, "type": "playlist"}
                            _LOGGER.info(
                                "✅ SEARCH RESULT (user library - exact match): %s", result)
                            return result

                    # Partial match in library
                    for playlist in user_playlists:
                        if hasattr(playlist, "name") and query_cleaned in playlist.name.lower():
                            result = {"uri": playlist.uri,
                                      "name": playlist.name, "type": "playlist"}
                            _LOGGER.info(
                                "✅ SEARCH RESULT (user library - partial match): %s", result)
                            return result

                except Exception as err:
                    _LOGGER.warning("Error searching user playlists: %s", err)

                # 2. Fallback to Public Search
                results = await client.search(query_cleaned, ["playlist"], limit=10)
                items_list = results.playlists
                if items_list and len(items_list) > 0:
                    selected_playlist = items_list[0]
                    result = {"uri": selected_playlist.uri,
                              "name": selected_playlist.name, "type": "playlist"}
                    _LOGGER.info(
                        "✅ SEARCH RESULT (public playlist - first result): %s", result)
                    return result
                else:
                    error_result = {"error": f"No playlist found for: {query}"}
                    _LOGGER.error("❌ SEARCH ERROR: %s", error_result)
                    return error_result

            elif search_type == "show":
                # Podcast show search — returns the show URI (spotify:show:xxx).
                # Spotify will resume the user's last position or play the latest
                # episode when started via context_uri.
                results = await client.search(query, ["show"], limit=10)
                items_list = results.shows
                if items_list and len(items_list) > 0:
                    # Prefer exact name match, fall back to first result
                    query_lower = query.lower()
                    exact_match = None
                    for show in items_list:
                        if hasattr(show, "name") and show.name.lower() == query_lower:
                            exact_match = show
                            break
                    selected = exact_match if exact_match else items_list[0]
                    result = {"uri": selected.uri, "name": selected.name, "type": "show"}
                    match_type = "exact match" if exact_match else "first result"
                    _LOGGER.info("✅ SEARCH RESULT (show - %s): %s", match_type, result)
                    return result
                else:
                    error_result = {"error": f"No podcast found for: {query}"}
                    _LOGGER.error("❌ SEARCH ERROR: %s", error_result)
                    return error_result

            elif search_type == "episode":
                # Single episode search — returns the episode URI (spotify:episode:xxx).
                # Useful for "play the latest episode of X" — searches episodes
                # and returns the top result, which Spotify ranks by recency.
                results = await client.search(query, ["episode"], limit=5)
                items_list = results.episodes
                if items_list and len(items_list) > 0:
                    episode = items_list[0]
                    result = {"uri": episode.uri, "name": episode.name, "type": "episode"}
                    _LOGGER.info("✅ SEARCH RESULT (episode - first result): %s", result)
                    return result
                else:
                    error_result = {"error": f"No episode found for: {query}"}
                    _LOGGER.error("❌ SEARCH ERROR: %s", error_result)
                    return error_result

            else:
                # Handle Album and Track
                results = await client.search(query, [search_type], limit=10)
                items_list = getattr(results, f"{search_type}s", None)

                if items_list and len(items_list) > 0:
                    exact_match = None
                    query_lower = query.lower()
                    for item in items_list:
                        if hasattr(item, "name") and item.name.lower() == query_lower:
                            exact_match = item
                            break

                    # Fallback logic for Albums
                    if not exact_match and search_type == "album" and len(query.split()) >= 2:
                        _LOGGER.info(
                            "No exact album match for '%s', trying track search", query)
                        try:
                            track_results = await client.search(query, ["track"], limit=10)
                            track_items = getattr(
                                track_results, "tracks", None)
                            if track_items and len(track_items) > 0:
                                first_track = track_items[0]
                                result = {"uri": first_track.uri,
                                          "name": first_track.name, "type": "track"}
                                _LOGGER.info(
                                    "✅ SEARCH RESULT (album→track fallback): %s", result)
                                return result
                        except Exception:
                            pass

                    selected_item = exact_match if exact_match else items_list[0]
                    match_type = "exact match" if exact_match else "first result"
                    result = {"uri": selected_item.uri,
                              "name": selected_item.name, "type": search_type}
                    _LOGGER.info("✅ SEARCH RESULT (%s - %s): %s",
                                 search_type, match_type, result)
                    return result
                else:
                    error_result = {
                        "error": f"No {search_type} found for: {query}"}
                    _LOGGER.error("❌ SEARCH ERROR: %s", error_result)
                    return error_result

        except Exception as err:
            _LOGGER.exception("Unexpected error searching Spotify")
            return {"error": "Search failed"}

    async def play_on_device(call: ServiceCall):
        """Start playback of a URI on a named Spotify Connect device.

        Strategy:
          1. Try get_devices() to find the device by name and get its ID.
          2. If device not found (librespot session ≠ HA OAuth session), fall back
             to HA's media_player.select_source to transfer playback to the device
             by name, then call start_playback without a device_id (targets the
             now-active device).

        Parameters:
            uri:         Spotify URI (spotify:artist:xxx, spotify:track:xxx, etc.)
            device_name: Name of the Spotify Connect device (e.g. "Naboo")
        """
        uri = call.data.get("uri")
        device_name = call.data.get("device_name", "Naboo")

        if not uri:
            _LOGGER.error("No URI provided to spotify_voice_assistant.play")
            return {"error": "No URI provided"}

        try:
            client = await get_spotify_client()
        except (LookupError, AttributeError) as err:
            _LOGGER.error("Failed to get Spotify client for playback: %s", err)
            return {"error": str(err)}

        try:
            # ── Step 1: try to find the device via API ────────────────────────
            devices = await client.get_devices()
            target_device = None
            for device in devices:
                if hasattr(device, "name") and device.name == device_name:
                    target_device = device
                    break

            device_id = None
            if target_device:
                device_id = (
                    getattr(target_device, "device_id", None)
                    or getattr(target_device, "id", None)
                )
                _LOGGER.info("▶ Found device '%s' via get_devices() (id=%s)", device_name, device_id)
            else:
                # ── Step 2: device not in get_devices() ──────────────────────
                # This happens when librespot's Spotify session ≠ HA's OAuth
                # token — the two authenticate independently and Spotify only
                # returns devices visible to the calling token's session.
                #
                # However, HA's Spotify coordinator tracks the currently active
                # device internally (it's what populates the 'source' attribute).
                # We dig the device ID out of the coordinator's current data,
                # which was obtained via the coordinator's own token — so it
                # matches whatever device librespot registered with.
                device_names = [d.name for d in devices if hasattr(d, "name")]
                _LOGGER.warning(
                    "Device '%s' not in get_devices() (available: %s). "
                    "Trying coordinator current_playback fallback.",
                    device_name, device_names
                )

                try:
                    entity_component = hass.data.get("entity_components", {}).get("media_player")
                    if entity_component:
                        for entity in entity_component.entities:
                            if "spotify" in entity.entity_id.lower():
                                # HA Spotify entity stores coordinator data
                                coordinator = getattr(entity, "coordinator", None)
                                if coordinator:
                                    data = getattr(coordinator, "data", None)
                                    if data:
                                        # coordinator.data.current_playback.device
                                        current_playback = getattr(data, "current_playback", None)
                                        if current_playback:
                                            dev = getattr(current_playback, "device", None)
                                            if dev:
                                                dev_name = getattr(dev, "name", None)
                                                dev_id = (
                                                    getattr(dev, "id", None)
                                                    or getattr(dev, "device_id", None)
                                                )
                                                _LOGGER.info(
                                                    "Coordinator active device: '%s' (id=%s)",
                                                    dev_name, dev_id
                                                )
                                                # Use this device if it matches, or use
                                                # it anyway since it's the active device
                                                # and we want to redirect playback to it
                                                if dev_id:
                                                    if dev_name == device_name:
                                                        device_id = dev_id
                                                        _LOGGER.info(
                                                            "✅ Got device ID from coordinator: %s",
                                                            device_id
                                                        )
                                                    else:
                                                        # Active device is something else —
                                                        # log it but proceed without device_id
                                                        # so start_playback targets the active device
                                                        _LOGGER.warning(
                                                            "Active device is '%s', not '%s' — "
                                                            "start_playback will target active device",
                                                            dev_name, device_name
                                                        )
                except Exception as coord_err:
                    _LOGGER.warning("Coordinator fallback failed: %s", coord_err)

                if not device_id:
                    _LOGGER.warning(
                        "No device ID found — calling start_playback without device_id "
                        "(Spotify will target the currently active device)"
                    )

            _LOGGER.info("▶ Starting playback on %s (id=%s): %s", device_name, device_id, uri)

            # Track and episode URIs use the uris param (single item playback).
            # Everything else (artist, album, playlist, show, collection) is a context.
            if uri.startswith("spotify:track:") or uri.startswith("spotify:episode:"):
                await client.start_playback(
                    **({} if not device_id else {"device_id": device_id}),
                    uris=[uri]
                )
            else:
                await client.start_playback(
                    **({} if not device_id else {"device_id": device_id}),
                    context_uri=uri
                )

            # Reconnect naboo to the librespot HTTP stream on every voice-initiated
            # play. Guards against stream orphaning after HA restarts or radio use.
            radio_active = hass.states.get("input_boolean.radio_active")
            if radio_active is None or radio_active.state != "on":
                _LOGGER.info("↔ Reconnecting naboo to HTTP stream after play command")
                hass.async_create_task(
                    hass.services.async_call(
                        "media_player",
                        "play_media",
                        {
                            "entity_id": "media_player.home_assistant_voice_0a3a76_media_player",
                            "media_content_id": "http://192.168.1.70:8765",
                            "media_content_type": "music",
                        },
                    )
                )
            else:
                _LOGGER.info("↔ Skipping naboo reconnect — radio is active")

            return {"success": True, "device": device_name, "uri": uri}

        except Exception as err:
            _LOGGER.exception("Error starting playback on %s", device_name)
            return {"error": f"Playback failed: {err}"}

    async def pause_playback(call: ServiceCall):
        """Pause Spotify playback on the active device.

        Used to stop Spotify from asserting over other audio sources
        (e.g., radio via Music Assistant) on shared speakers.
        """
        try:
            client = await get_spotify_client()
        except (LookupError, AttributeError) as err:
            _LOGGER.warning("Cannot pause Spotify — no client: %s", err)
            return {"error": str(err)}

        try:
            await client.pause_playback()
            _LOGGER.info("⏸ Paused Spotify playback")
            return {"success": True}
        except Exception as err:
            # Not fatal — Spotify may already be paused or no active device
            _LOGGER.warning("Could not pause Spotify: %s", err)
            return {"error": f"Pause failed: {err}"}

    async def resume_playback(call: ServiceCall):
        """Resume Spotify playback on the active device (no URI — continues current context).

        Calls start_playback() with no arguments, which is the Spotify Web API
        equivalent of pressing Play on a paused session. librespot will fire a
        'playing' event → on_event.sh → librespot_playing webhook → ESPHome plays
        the HTTP stream on Naboo — same chain as a fresh spotify_voice_assistant.play.
        """
        try:
            client = await get_spotify_client()
        except (LookupError, AttributeError) as err:
            _LOGGER.warning("Cannot resume Spotify — no client: %s", err)
            return {"error": str(err)}

        try:
            await client.playback_resume()
            _LOGGER.info("▶ Resumed Spotify playback")
            return {"success": True}
        except Exception as err:
            _LOGGER.warning("Could not resume Spotify: %s", err)
            return {"error": f"Resume failed: {err}"}

    async def clear_cache(call: ServiceCall):
        """Clear Spotify client and user playlists cache."""
        if _spotify_cache["client"] is not None or _spotify_cache["user_playlists"] is not None:
            _spotify_cache["client"] = None
            _spotify_cache["entity_id"] = None
            _spotify_cache["user_playlists"] = None
            return {"success": True, "message": "Cache cleared"}
        else:
            return {"success": False, "message": "Cache was already empty"}

    async def podcast_play(call: ServiceCall):
        """Play the latest episode of a podcast directly on naboo via RSS.

        Bypasses librespot/Spotify entirely — librespot cannot decode podcast
        episode audio keys (known unfixed bug: 'error audio key 0 1').

        Flow:
          1. iTunes Search API → find podcast by name → get RSS feed URL
          2. Fetch RSS XML → extract latest episode <enclosure url="...">
          3. media_player.play_media on naboo_media_player with the direct URL

        This path has zero impact on existing Spotify music / radio commands.
        """
        import aiohttp

        raw_query = call.data.get("query", "").strip()
        if not raw_query:
            _LOGGER.error("podcast_play: no query provided")
            return {"error": "No query provided"}

        # Strip common noise words before hitting iTunes
        query = raw_query.lower()
        for noise in ("podcast ", "the podcast ", "play ", "listen to "):
            if query.startswith(noise):
                query = query[len(noise):]
        query = " ".join(query.split())

        _LOGGER.info("🎙 podcast_play: searching iTunes for '%s' (raw: '%s')", query, raw_query)

        import urllib.parse
        itunes_url = (
            "https://itunes.apple.com/search?"
            + urllib.parse.urlencode({
                "term": query,
                "media": "podcast",
                "entity": "podcast",
                "limit": "5",
            })
        )

        try:
            async with aiohttp.ClientSession() as session:
                # ── Step 1: Find podcast on iTunes ────────────────────────────
                async with session.get(itunes_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        _LOGGER.error("podcast_play: iTunes API returned %s", resp.status)
                        return {"error": f"iTunes API error: {resp.status}"}
                    itunes_data = await resp.json(content_type=None)

                results = itunes_data.get("results", [])
                if not results:
                    _LOGGER.error("podcast_play: no iTunes results for '%s'", query)
                    return {"error": f"No podcast found for: {query}"}

                # Prefer exact name match, otherwise take first result
                query_lower = query.lower()
                feed_url = None
                podcast_name = None
                for r in results:
                    if r.get("collectionName", "").lower() == query_lower:
                        feed_url = r.get("feedUrl")
                        podcast_name = r.get("collectionName")
                        break
                if not feed_url:
                    feed_url = results[0].get("feedUrl")
                    podcast_name = results[0].get("collectionName")

                if not feed_url:
                    _LOGGER.error("podcast_play: no feedUrl in iTunes result for '%s'", query)
                    return {"error": f"No RSS feed found for: {query}"}

                _LOGGER.info("podcast_play: found '%s' feed: %s", podcast_name, feed_url)

                # ── Step 2: Fetch RSS and extract latest episode URL ──────────
                async with session.get(feed_url, timeout=aiohttp.ClientTimeout(total=10)) as rss_resp:
                    if rss_resp.status != 200:
                        _LOGGER.error("podcast_play: RSS fetch returned %s for %s", rss_resp.status, feed_url)
                        return {"error": f"RSS fetch failed: {rss_resp.status}"}
                    rss_text = await rss_resp.text()

            root = ET.fromstring(rss_text)
            channel = root.find("channel")
            if channel is None:
                _LOGGER.error("podcast_play: no <channel> in RSS for %s", feed_url)
                return {"error": "Invalid RSS feed"}

            # Walk items in order — first item is the latest episode
            episode_url = None
            episode_title = None
            for item in channel.findall("item"):
                enclosure = item.find("enclosure")
                if enclosure is not None:
                    url = enclosure.get("url", "")
                    # Only accept audio content
                    enc_type = enclosure.get("type", "")
                    if url and ("audio" in enc_type or url.endswith((".mp3", ".m4a", ".ogg", ".aac"))):
                        episode_url = url
                        title_el = item.find("title")
                        episode_title = title_el.text if title_el is not None else "unknown"
                        break

            if not episode_url:
                _LOGGER.error("podcast_play: no audio enclosure found in RSS for %s", feed_url)
                return {"error": "No audio episode found in RSS feed"}

            _LOGGER.info(
                "podcast_play: ▶ playing episode '%s' from '%s': %s",
                episode_title, podcast_name, episode_url
            )

        except aiohttp.ClientError as err:
            _LOGGER.error("podcast_play: network error: %s", err)
            return {"error": f"Network error: {err}"}
        except ET.ParseError as err:
            _LOGGER.error("podcast_play: RSS parse error: %s", err)
            return {"error": f"RSS parse error: {err}"}
        except Exception as err:
            _LOGGER.exception("podcast_play: unexpected error")
            return {"error": f"Unexpected error: {err}"}

        # ── Step 3: Play on naboo directly (bypasses librespot) ───────────────
        try:
            # Pause any active Spotify playback to avoid librespot reasserting
            try:
                client = await get_spotify_client()
                await client.pause_playback()
                _LOGGER.info("podcast_play: paused Spotify before RSS playback")
            except Exception:
                pass  # Not fatal — Spotify may already be idle

            await hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": "media_player.home_assistant_voice_0a3a76_media_player",
                    "media_content_id": episode_url,
                    "media_content_type": "music",
                },
            )
            _LOGGER.info("✅ podcast_play: sent play_media to naboo for '%s'", episode_title)
            return {"success": True, "podcast": podcast_name, "episode": episode_title, "url": episode_url}

        except Exception as err:
            _LOGGER.exception("podcast_play: failed to call media_player.play_media")
            return {"error": f"play_media failed: {err}"}

    hass.services.async_register(
        DOMAIN, "search", search_spotify, supports_response="only"
    )
    hass.services.async_register(
        DOMAIN, "play", play_on_device, supports_response="optional"
    )
    hass.services.async_register(
        DOMAIN, "pause", pause_playback, supports_response="optional"
    )
    hass.services.async_register(
        DOMAIN, "resume", resume_playback, supports_response="optional"
    )
    hass.services.async_register(
        DOMAIN, "clear_cache", clear_cache, supports_response="only"
    )
    hass.services.async_register(
        DOMAIN, "podcast_play", podcast_play, supports_response="optional"
    )
    return True
