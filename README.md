# unseenet-demo

Demo content for [Unseenet](https://unseenet.org), so there is something to see: a
site with pages, pictures and links, feeds to follow, and a handful of fictional
people who post and comment on each other.

It is made **only with the `unseenet` command-line client**, so it is also a proof
of concept: everything here is something anyone can do with the released software.

> Status: being planned for Unseenet 0.5.0 (unseenet#385). Nothing to run yet.

## The idea

- **Content as files.** Pages in Markdown, feed entries, comments, profiles and the
  pictures, under `content/`. Change a file and run the script again.
- **One script.** `demo.py up` creates the groups, profiles, posts, comments, pins
  and pages that are missing; `demo.py reset` withdraws what it posted and posts it
  again; `demo.py down` withdraws everything, and `down --remove-groups` removes the
  groups for good (their names cannot be used again afterwards, so a new demo then
  gets new names).
- **Fictional people.** Their keys are derived from one secret demo key, which is
  never in this repository. Their key-ripening chains need no secret and are kept
  here, so a run does not ripen again.

## Running it

Needs the `unseenet` CLI (0.5.0 or later), Tor, and the demo key
(`UNSEENET_DEMO_SEED`), which the maintainer keeps with the project's other keys.

## License

Code: Apache-2.0. Content (text and pictures): CC BY 4.0.
