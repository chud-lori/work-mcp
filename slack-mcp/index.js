#!/usr/bin/env node
/**
 * Slack MCP server (read-only).
 *
 * Auth: reads SLACK_USER_TOKEN (xoxp-...) from the environment, or from a
 * .env file sitting next to this script. Runs as that user, so it sees
 * whatever the user can see. A bot token (SLACK_BOT_TOKEN) also works as a
 * fallback, but message search is only available with a user token.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// --- token loading -----------------------------------------------------

function loadDotEnv() {
  try {
    const envPath = join(dirname(fileURLToPath(import.meta.url)), ".env");
    for (const line of readFileSync(envPath, "utf8").split("\n")) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
      if (m && !process.env[m[1]]) {
        process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
      }
    }
  } catch {
    // no .env file — rely on the environment
  }
}
loadDotEnv();

const TOKEN = process.env.SLACK_USER_TOKEN || process.env.SLACK_BOT_TOKEN;

if (!TOKEN) {
  console.error(
    "slack-mcp: SLACK_USER_TOKEN is not set. Export it or put it in " +
      join(dirname(fileURLToPath(import.meta.url)), ".env")
  );
  process.exit(1);
}

// search.messages only works with a user token
const SEARCH_ENABLED = TOKEN.startsWith("xoxp");

// --- Slack API helper --------------------------------------------------

async function slack(method, params = {}) {
  const body = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) body.set(k, String(v));
  }
  const res = await fetch(`https://slack.com/api/${method}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });
  const data = await res.json();
  if (!data.ok) {
    throw new Error(`Slack API ${method} failed: ${data.error}`);
  }
  return data;
}

function text(obj) {
  return { content: [{ type: "text", text: JSON.stringify(obj, null, 2) }] };
}

function richTextElement(el) {
  if (!el) return "";
  switch (el.type) {
    case "text":
      return el.text;
    case "link":
      return el.text ? `${el.text} (${el.url})` : el.url;
    case "user":
      return `<@${el.user_id}>`;
    case "channel":
      return `<#${el.channel_id}>`;
    case "usergroup":
      return `<!subteam^${el.usergroup_id}>`;
    case "emoji":
      return `:${el.name}:`;
    case "broadcast":
      return `@${el.range}`;
    case "date":
      return el.fallback ?? String(el.timestamp);
    case "color":
      return el.value;
    case "rich_text_section":
    case "rich_text_preformatted":
    case "rich_text_quote":
      return (el.elements ?? []).map(richTextElement).join("");
    case "rich_text_list":
      return (el.elements ?? [])
        .map((item, i) => {
          const marker = el.style === "ordered" ? `${(el.offset ?? 0) + i + 1}.` : "-";
          return `${"  ".repeat(el.indent ?? 0)}${marker} ${richTextElement(item)}`;
        })
        .join("\n");
    default:
      return `[${el.type}] ${JSON.stringify(el).slice(0, 500)}`;
  }
}

function blockText(block) {
  if (!block) return "";
  switch (block.type) {
    case "rich_text":
      return (block.elements ?? []).map(richTextElement).join("\n");
    case "section":
      return [block.text?.text, ...(block.fields ?? []).map((f) => f.text)]
        .filter(Boolean)
        .join("\n");
    case "header":
      return block.text?.text ?? "";
    case "context":
      return (block.elements ?? []).map((e) => e.text).filter(Boolean).join(" ");
    case "markdown":
      return block.text ?? "";
    case "table":
      return (block.rows ?? [])
        .map((row) => `| ${row.map(tableCell).join(" | ")} |`)
        .join("\n");
    case "actions":
      return (block.elements ?? [])
        .map((e) => [e.text?.text, e.url].filter(Boolean).join(" "))
        .filter(Boolean)
        .map((s) => `[${s}]`)
        .join(" ");
    case "image":
      return `[image: ${block.title?.text || block.alt_text || ""} ${block.image_url ?? block.slack_file?.url ?? ""}]`;
    case "video":
      return `[video: ${block.title?.text ?? ""} ${block.title_url ?? block.video_url ?? ""}]`;
    case "file":
      return `[file: ${block.external_id ?? block.file_id ?? ""}]`;
    case "divider":
      return "";
    default:
      // Unknown block types are dumped so their content is never silently lost.
      return `[${block.type} block] ${JSON.stringify(block).slice(0, 2000)}`;
  }
}

function tableCell(cell) {
  if (!cell) return "";
  if (cell.type === "raw_text") return cell.text ?? "";
  if (cell.type === "rich_text") return (cell.elements ?? []).map(richTextElement).join(" ");
  return cell.text ?? "";
}

// Slack's `text` can drop rich-text content such as list items.
function blocksText(m) {
  let out;
  try {
    out = (m.blocks ?? []).map(blockText).filter(Boolean).join("\n").trim();
  } catch (err) {
    // One malformed block must not fail the whole thread read.
    return `[blocks unreadable: ${err.message}] ${JSON.stringify(m.blocks).slice(0, 2000)}`;
  }
  return out && out !== m.text?.trim() ? out : undefined;
}

function slimAttachment(a) {
  return {
    title: a.title,
    title_link: a.title_link,
    text: a.text || a.fallback,
    from_url: a.from_url,
    service_name: a.service_name,
    blocks_text: a.blocks ? blocksText({ blocks: a.blocks, text: a.text }) : undefined,
  };
}

function slimMessage(m) {
  return {
    ts: m.ts,
    thread_ts: m.thread_ts,
    user: m.user ?? m.bot_id,
    text: m.text,
    blocks_text: blocksText(m),
    attachments: m.attachments?.map(slimAttachment),
    reply_count: m.reply_count,
    reactions: m.reactions?.map((r) => `${r.name}:${r.count}`),
    files: m.files?.map((f) => ({
      id: f.id,
      name: f.name,
      mimetype: f.mimetype,
      size: f.size,
    })),
  };
}

// Resolve "#general" / "general" / "C0123ABC" to a channel ID.
async function resolveChannel(channel) {
  const name = channel.replace(/^#/, "");
  if (/^[CDG][A-Z0-9]{8,}$/.test(name)) return name;
  let cursor;
  do {
    const data = await slack("conversations.list", {
      types: "public_channel,private_channel",
      limit: 200,
      cursor,
    });
    const hit = data.channels.find((c) => c.name === name);
    if (hit) return hit.id;
    cursor = data.response_metadata?.next_cursor || undefined;
  } while (cursor);
  throw new Error(`Channel not found: ${channel}`);
}

// --- server ------------------------------------------------------------

const server = new McpServer({ name: "slack", version: "1.0.0" });

server.tool(
  "slack_list_channels",
  "List Slack channels the bot can see",
  {
    limit: z.number().optional().describe("Max channels to return (default 100)"),
    cursor: z.string().optional().describe("Pagination cursor from a previous call"),
  },
  async ({ limit = 100, cursor }) => {
    const data = await slack("conversations.list", {
      types: "public_channel,private_channel",
      exclude_archived: true,
      limit,
      cursor,
    });
    return text({
      channels: data.channels.map((c) => ({
        id: c.id,
        name: c.name,
        is_private: c.is_private,
        num_members: c.num_members,
        topic: c.topic?.value || undefined,
      })),
      next_cursor: data.response_metadata?.next_cursor || undefined,
    });
  }
);

server.tool(
  "slack_get_channel_history",
  "Read recent messages from a channel (by name or ID)",
  {
    channel: z.string().describe("Channel name (e.g. #general) or ID (C...)"),
    limit: z.number().optional().describe("Max messages (default 30)"),
    oldest: z.string().optional().describe("Only messages after this Unix timestamp"),
  },
  async ({ channel, limit = 30, oldest }) => {
    const id = await resolveChannel(channel);
    const data = await slack("conversations.history", { channel: id, limit, oldest });
    return text({ channel: id, messages: data.messages.map(slimMessage) });
  }
);

server.tool(
  "slack_get_thread_replies",
  "Read all replies in a message thread",
  {
    channel: z.string().describe("Channel name or ID"),
    thread_ts: z.string().describe("Timestamp (ts) of the thread's parent message"),
  },
  async ({ channel, thread_ts }) => {
    const id = await resolveChannel(channel);
    const data = await slack("conversations.replies", { channel: id, ts: thread_ts });
    return text({ messages: data.messages.map(slimMessage) });
  }
);

server.tool(
  "slack_list_users",
  "List workspace members",
  {
    limit: z.number().optional().describe("Max users (default 100)"),
    cursor: z.string().optional().describe("Pagination cursor"),
  },
  async ({ limit = 100, cursor }) => {
    const data = await slack("users.list", { limit, cursor });
    return text({
      users: data.members
        .filter((u) => !u.deleted && !u.is_bot && u.id !== "USLACKBOT")
        .map((u) => ({
          id: u.id,
          name: u.name,
          real_name: u.profile?.real_name,
          email: u.profile?.email,
          title: u.profile?.title || undefined,
        })),
      next_cursor: data.response_metadata?.next_cursor || undefined,
    });
  }
);

server.tool(
  "slack_get_user",
  "Get a user's profile by user ID",
  { user_id: z.string().describe("Slack user ID (U...)") },
  async ({ user_id }) => {
    const data = await slack("users.info", { user: user_id });
    const u = data.user;
    return text({
      id: u.id,
      name: u.name,
      real_name: u.profile?.real_name,
      email: u.profile?.email,
      title: u.profile?.title,
      tz: u.tz,
    });
  }
);

const VIEWABLE_IMAGES = ["image/png", "image/jpeg", "image/gif", "image/webp"];
const MAX_FILE_BYTES = 3 * 1024 * 1024;

server.tool(
  "slack_get_file",
  "Download a file shared in Slack by its file ID (from the `files` field of a message). Images are returned so they can be viewed directly; text files are returned as text.",
  { file_id: z.string().describe("Slack file ID (F...)") },
  async ({ file_id }) => {
    const info = await slack("files.info", { file: file_id });
    const f = info.file;
    if (f.size > MAX_FILE_BYTES) {
      throw new Error(
        `File ${f.name} is ${Math.round(f.size / 1024)}KB — too large to return (limit ${MAX_FILE_BYTES / 1024}KB)`
      );
    }
    const res = await fetch(f.url_private, {
      headers: { Authorization: `Bearer ${TOKEN}` },
    });
    if (!res.ok) throw new Error(`Download failed: HTTP ${res.status}`);
    const buf = Buffer.from(await res.arrayBuffer());
    if (VIEWABLE_IMAGES.includes(f.mimetype)) {
      return {
        content: [
          { type: "text", text: `${f.name} (${f.mimetype}, ${buf.length} bytes)` },
          { type: "image", data: buf.toString("base64"), mimeType: f.mimetype },
        ],
      };
    }
    if (
      f.mimetype.startsWith("text/") ||
      ["application/json", "application/xml", "application/javascript"].includes(f.mimetype)
    ) {
      return { content: [{ type: "text", text: buf.toString("utf8") }] };
    }
    throw new Error(
      `File type ${f.mimetype} can't be displayed. Permalink: ${f.permalink}`
    );
  }
);

if (SEARCH_ENABLED) {
  server.tool(
    "slack_search_messages",
    "Search messages across the workspace",
    {
      query: z.string().describe("Search query, supports Slack modifiers like in:#channel from:@user"),
      count: z.number().optional().describe("Max results (default 20)"),
    },
    async ({ query, count = 20 }) => {
      const data = await slack("search.messages", { query, count });
      return text({
        total: data.messages.total,
        matches: data.messages.matches.map((m) => ({
          channel: m.channel?.name,
          user: m.username,
          ts: m.ts,
          text: m.text,
          blocks_text: blocksText(m),
          permalink: m.permalink,
        })),
      });
    }
  );
}

const transport = new StdioServerTransport();
await server.connect(transport);
console.error("slack-mcp: server running on stdio");
