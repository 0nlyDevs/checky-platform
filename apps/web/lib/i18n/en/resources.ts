// English for the newsroom resources (mirrors fr/resources.ts). Machine-drafted, to be reread.
import type { resources as fr } from "../fr/resources";
import type { Part } from "../mg/part";

export const resources: Part<typeof fr> = {
  contacts: { title: "Directory", lead: "Who can answer your question precisely? These contacts are entered by your newsroom, with no automatic certification." },
  registry: { title: "Registry of originals", lead: "Keep the original text and link to compare against the documents going around. A record is not a certification." },
  figures: { title: "Figures", lead: "Figures to quote with their period, territory and source. An old observation stays dated as such." },
  radio: { title: "On air", lead: "Note what you heard, where and when. For Malagasy, your summary stays human; Checky looks for the available evidence." },
  new: "Add", save: "Save", saving: "Saving…", cancel: "Cancel", search: "Search", empty: "Nothing here yet.", failed: "Couldn't load this data.", retry: "Try again", saved: "Saved", denied: "This action isn't possible here.", source: "View the source", call: "Call", email: "Write", check: "Look for evidence", unknown: "Declared details, not verified", number: "Document number", error: "Check the fields and try again.",
  fields: { name: "Name", role: "Role / expertise", institution: "Institution", phone: "Work phone", email: "Work email", website: "Declared official page", issuer: "Issuer", title: "Title", number: "Reference (optional)", text: "Full text", url: "Link to the original", topic: "Topic", label: "Indicator", value: "Value", unit: "Unit", as_of: "Period observed (YYYY or YYYY-MM-DD)", country: "Country / territory", source_name: "Source body", source_url: "Source link", station: "Station / programme", heard_text: "In one sentence, what did you hear?", language: "Language heard (mg, fr, en…)", recorded_at: "Date and time heard", source_id: "ID of the clip already added to Sources (optional)" },
  rubrique: "My beat", rubriqueLead: "Your recent cases, filtered by your newsroom's topics.", beats: "My topics (comma-separated)", all: "No filter: all cases", open: "Open the case", verify: "Check a piece of information", shelves: "The log", documents: "Documents and sources", angles: "Explore an angle", anglesLead: "Start from a topic, then ask your documents. Angles are working leads; their premises must be sourced.", angleTopic: "Your topic", angleAction: "Ask our sources", anglePrompt: "Using the available sources, suggest three journalistic angles on: ",
};
