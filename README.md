<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/unseenet/unseenet/main/assets/logo-dark.svg">
    <img src="https://raw.githubusercontent.com/unseenet/unseenet/main/assets/logo-light.svg" alt="Unseenet" width="360">
  </picture>
</p>

<h1 align="center">unseenet-demo</h1>

<p align="center"><b>Demo content for Unseenet, so there is something to see.</b><br>
Made-up people with profiles, feeds and sites, chats and discussions - all made with the command-line client.</p>

<p align="center">
  <a href="https://github.com/unseenet/unseenet-demo/actions/workflows/weekly.yml"><img src="https://github.com/unseenet/unseenet-demo/actions/workflows/weekly.yml/badge.svg" alt="weekly"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0"></a>
</p>

> **Pre-alpha.** Nothing is stable yet, and Unseenet has not had a security
> review. Do not rely on it to protect anyone yet.

## What it is

Demo content for [Unseenet](https://unseenet.org), so there is something to see: five
made-up people with profiles, pictures and their own feeds and sites, a shared feed, a chat, a
discussion group, a photo group and a site - with comments and replies between them.

It is made **only with the `unseenet` command-line client**, so it is also a proof of
concept: everything here is something anyone can do with the released software.

| Group | What |
|---|---|
| `unseenet.demo` | a discussion group: threads and replies, a pinned welcome |
| `unseenet.demo.chat` | a chat room |
| `unseenet.demo.feed` | "Around the village", a shared feed with comments open |
| `unseenet.demo.photos` | pictures, with their metadata taken out by the client |
| `unseenet.demo.site` | the demo's site: pages that stay, with links to everything |
| `feed@<fingerprint>` | each person's personal feed |
| `site@<fingerprint>` | each person's personal site: a home page and a page about what they care about |

The people - Mira and her guinea pigs, Tomas the beekeeper, Nadia the baker, Ole the
radio amateur and Ines who walks and looks at stars - are in `content/people.toml`;
their posts in `content/posts.toml`, the chat in `content/chat.toml`, the site's pages
in `content/site/`, and each person's own site in `content/people/<name>/`. Every group's charter says that **everything is reset every Monday**.

### Pictures

From [Wikimedia Commons](https://commons.wikimedia.org/), only public domain, CC0 and
plain CC BY - see [CREDITS.md](CREDITS.md). Every post with a picture says where it
comes from. `tools/fetch_pictures.py` finds and downloads them, and writes the credits.

## Run it

Needs the `unseenet` CLI (0.5.0 or later), a node to post to, and the demo seed.

```bash
python demo.py up        # make what is missing (safe to run again)
python demo.py reset     # withdraw everything - also what others wrote - and make it again
python demo.py down      # withdraw everything; --remove-groups removes the groups for good
```

Settings are in `demo.toml` (`DEMO_CONFIG` names another file): the group prefix, the
node, where the vault and the state are kept, and where the seed is.

**The seed** is 64 hex characters, in `UNSEENET_DEMO_SEED` or the file `seed_file`
names. Every person's key is derived from it and their name (HMAC-SHA256), so the same
seed always gives the same people. It is never in this repository; the maintainer keeps
it with the project's other keys.

**The first run** takes a while: every new key works for a few minutes, once, before it
posts (key ripening, UN-RFC 0025). After that the vault remembers.

**Riper keys** (`tools/ripen.py start`): every person's key ripens further in the
background, at the lowest priority, to `--to`, else `UNSEENET_RIPEN_TO`, else `ripen_to`
in `demo.toml`, else level 2. Level 4 takes about a month of one core per person and
then makes every post about four times cheaper than level 2 - worth it on a machine with
cores to spare. `status` shows how far each key is; `stop` keeps the progress.

**What has been made** is remembered in the state file, so `up` makes only what is
missing, and `reset` knows what to make again.

## Versions and releases

Not released: GitHub Actions runs it from `main` every week (`weekly.yml`),
and new posts for its pool come as pull requests (`write.yml`).

## Part of Unseenet

| Repository | What it is |
|---|---|
| [unseenet](https://github.com/unseenet/unseenet) | The protocol (UN-RFCs), the core library, the node and the command-line client |
| [unseenet-tui](https://github.com/unseenet/unseenet-tui) | The terminal client |
| [unseenet-gui](https://github.com/unseenet/unseenet-gui) | The graphical client - in a window, booted, or in a browser |
| [unseenet-portable](https://github.com/unseenet/unseenet-portable) | Builds the portable clients, Terminal and Graphical, with Tor inside |
| [unseenet-bootable](https://github.com/unseenet/unseenet-bootable) | Builds the bootable images, Terminal and Graphical |
| [unseenet-docs](https://github.com/unseenet/unseenet-docs) | The site [unseenet.org](https://unseenet.org) |
| [unseenet-entrance](https://github.com/unseenet/unseenet-entrance) | Web entrances: the graphical client in an ordinary browser |
| [unseenet-gateway](https://github.com/unseenet/unseenet-gateway) | Gateways to other networks: Usenet, Nostr, Matrix |
| [unseenet-bots](https://github.com/unseenet/unseenet-bots) | Bots that keep channels filled with current content |
| [unseenet-helpbot](https://github.com/unseenet/unseenet-helpbot) | The bot that answers questions in `unseenet.help` |
| [unseenet-watchman](https://github.com/unseenet/unseenet-watchman) | Automatic spam reports and content labels that readers may choose to follow |
| [unseenet-stats](https://github.com/unseenet/unseenet-stats) | Statistics for the network |
| [unseenet-mcp](https://github.com/unseenet/unseenet-mcp) | An MCP server, so a language model can read and post as you (planning) |
| [unseenet-demo](https://github.com/unseenet/unseenet-demo) | Demo people, feeds and sites, made with the command-line client |

## License

[Apache License 2.0](LICENSE). The Unseenet logo: CC BY 4.0.
