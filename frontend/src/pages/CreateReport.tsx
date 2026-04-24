import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "@/components/AppShell";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/hooks/use-toast";
import { ApiError, extractRulesFromDocx, generateReport } from "@/lib/api";
import { ArrowLeft, Sparkles, Plus, Trash2, ChevronUp, ChevronDown, GripVertical } from "lucide-react";

const MAX_CONTENT = 100_000; // 100k chars guard
const MAX_FILE_BYTES = 50_000_000;

export interface DocumentSection {
  id: string;
  title: string;
  mode: "auto_generate" | "user_provides" | "skip";
}

type RuleOverrides = {
  bodyFont: string;
  bodySizePt: string;
  marginTopIn: string;
  marginLeftIn: string;
  marginBottomIn: string;
  marginRightIn: string;
  lineSpacingPt: string;
};

type CustomPreset = {
  overrides: RuleOverrides;
  category: string;
  tags: string[];
  createdAt: string;
};

type MetadataField = {
  id: string;
  key: string;
  value: string;
};

function createMetadataField(key = "", value = ""): MetadataField {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    key,
    value,
  };
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const base64 = result.includes(",") ? result.split(",")[1] : "";
      resolve(base64);
    };
    reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

export default function CreateReport() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [rules, setRules] = useState(
    "Use a formal academic tone. Include sections: Abstract, Introduction, Methodology, Results, Discussion, Conclusion, References. Use numbered headings."
  );
  const [content, setContent] = useState("");
  const [referenceContent, setReferenceContent] = useState("");
  const [contentFiles, setContentFiles] = useState<File[]>([]);
  const [referenceFiles, setReferenceFiles] = useState<File[]>([]);
  const [styleReferenceFile, setStyleReferenceFile] = useState<File | null>(null);
  const [ruleDocumentType, setRuleDocumentType] = useState("generic");
  const [ruleNotes, setRuleNotes] = useState("");
  const [rulesId, setRulesId] = useState("");
  const [rulesSummary, setRulesSummary] = useState<string>("");
  const [ruleValidationWarnings, setRuleValidationWarnings] = useState<string[]>([]);
  const [extractingRules, setExtractingRules] = useState(false);
  const [busy, setBusy] = useState(false);
  const [metadataFields, setMetadataFields] = useState<MetadataField[]>(() => [
    createMetadataField("author"),
    createMetadataField("subject"),
    createMetadataField("keywords"),
    createMetadataField("company"),
  ]);
  const [sections, setSections] = useState<DocumentSection[]>([
    { id: "1", title: "Introduction", mode: "auto_generate" },
    { id: "2", title: "Main Content", mode: "auto_generate" },
    { id: "3", title: "Conclusion", mode: "auto_generate" },
  ]);
  const [ruleOverrides, setRuleOverrides] = useState<RuleOverrides>({
    bodyFont: "",
    bodySizePt: "",
    marginTopIn: "",
    marginLeftIn: "",
    marginBottomIn: "",
    marginRightIn: "",
    lineSpacingPt: "",
  });
  const [showRuleOverrides, setShowRuleOverrides] = useState(false);
  const [showSavePreset, setShowSavePreset] = useState(false);
  const [newPresetName, setNewPresetName] = useState("");
  const [newPresetCategory, setNewPresetCategory] = useState("general");
  const [newPresetTags, setNewPresetTags] = useState("");
  const [defaultPresetName, setDefaultPresetName] = useState(() => localStorage.getItem("defaultCustomRulePreset") || "");
  const [importConflictStrategy, setImportConflictStrategy] = useState<"overwrite" | "skip" | "rename">("rename");
  const [presetSearchTerm, setPresetSearchTerm] = useState("");
  const [presetCategoryFilter, setPresetCategoryFilter] = useState("all");
  const [favoritePresetNames, setFavoritePresetNames] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem("favoriteCustomRulePresets");
      const parsed = saved ? JSON.parse(saved) : [];
      return Array.isArray(parsed) ? parsed.map((item) => String(item).trim()).filter(Boolean) : [];
    } catch {
      return [];
    }
  });
  const [renamingPresetName, setRenamingPresetName] = useState("");
  const [renamingPresetDraft, setRenamingPresetDraft] = useState("");
  const presetImportInputRef = useRef<HTMLInputElement | null>(null);
  const [customPresets, setCustomPresets] = useState<Record<string, CustomPreset>>(() => {
    try {
      const saved = localStorage.getItem("customRulePresets");
      if (!saved) return {};
      const parsed = JSON.parse(saved);
      if (!parsed || typeof parsed !== "object") return {};

      const normalized: Record<string, CustomPreset> = {};
      for (const [name, value] of Object.entries(parsed as Record<string, any>)) {
        if (!String(name).trim()) continue;
        if (value && typeof value === "object" && "overrides" in value) {
          normalized[String(name).trim()] = {
            overrides: {
              bodyFont: String((value as any).overrides?.bodyFont ?? ""),
              bodySizePt: String((value as any).overrides?.bodySizePt ?? ""),
              marginTopIn: String((value as any).overrides?.marginTopIn ?? ""),
              marginLeftIn: String((value as any).overrides?.marginLeftIn ?? ""),
              marginBottomIn: String((value as any).overrides?.marginBottomIn ?? ""),
              marginRightIn: String((value as any).overrides?.marginRightIn ?? ""),
              lineSpacingPt: String((value as any).overrides?.lineSpacingPt ?? ""),
            },
            category: String((value as any).category ?? "general"),
            tags: Array.isArray((value as any).tags)
              ? (value as any).tags.map((tag: any) => String(tag).trim()).filter(Boolean)
              : [],
            createdAt: String((value as any).createdAt ?? new Date().toISOString()),
          };
        } else {
          // Backward compatibility: previous versions stored overrides directly.
          normalized[String(name).trim()] = {
            overrides: {
              bodyFont: String((value as any)?.bodyFont ?? ""),
              bodySizePt: String((value as any)?.bodySizePt ?? ""),
              marginTopIn: String((value as any)?.marginTopIn ?? ""),
              marginLeftIn: String((value as any)?.marginLeftIn ?? ""),
              marginBottomIn: String((value as any)?.marginBottomIn ?? ""),
              marginRightIn: String((value as any)?.marginRightIn ?? ""),
              lineSpacingPt: String((value as any)?.lineSpacingPt ?? ""),
            },
            category: "legacy",
            tags: [],
            createdAt: new Date().toISOString(),
          };
        }
      }
      return normalized;
    } catch {
      return {};
    }
  });

  const addMetadataField = () => {
    setMetadataFields((current) => [...current, createMetadataField()]);
  };

  const updateMetadataField = (id: string, updates: Partial<MetadataField>) => {
    setMetadataFields((current) =>
      current.map((field) => (field.id === id ? { ...field, ...updates } : field))
    );
  };

  const removeMetadataField = (id: string) => {
    setMetadataFields((current) => current.filter((field) => field.id !== id));
  };

  const saveCustomPreset = (name: string) => {
    const normalizedName = name.trim();
    if (!normalizedName) {
      toast({
        title: "Invalid name",
        description: "Preset name cannot be empty.",
        variant: "destructive",
      });
      return;
    }

    const duplicateName = _findDuplicatePresetName(ruleOverrides, customPresets, normalizedName);
    if (duplicateName && duplicateName !== normalizedName) {
      toast({
        title: "Duplicate preset detected",
        description: `These overrides already match "${duplicateName}". Rename or change values before saving a new preset.`,
        variant: "destructive",
      });
      return;
    }

    const parsedTags = newPresetTags
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
    const updated = {
      ...customPresets,
      [normalizedName]: {
        overrides: ruleOverrides,
        category: newPresetCategory.trim() || "general",
        tags: parsedTags,
        createdAt: new Date().toISOString(),
      },
    };
    _persistCustomPresets(updated);
    if (!defaultPresetName) {
      setDefaultPresetName(normalizedName);
      localStorage.setItem("defaultCustomRulePreset", normalizedName);
    }
    setNewPresetName("");
    setNewPresetCategory("general");
    setNewPresetTags("");
    setShowSavePreset(false);

    toast({
      title: "Preset saved",
      description: `"${name}" has been saved and is now available.`,
    });
  };

  const _persistCustomPresets = (presets: Record<string, CustomPreset>) => {
    setCustomPresets(presets);
    localStorage.setItem("customRulePresets", JSON.stringify(presets));
  };

  const _persistFavoritePresetNames = (names: string[]) => {
    setFavoritePresetNames(names);
    localStorage.setItem("favoriteCustomRulePresets", JSON.stringify(names));
  };

  const _areOverridesEqual = (left: RuleOverrides, right: RuleOverrides) =>
    left.bodyFont === right.bodyFont &&
    left.bodySizePt === right.bodySizePt &&
    left.marginTopIn === right.marginTopIn &&
    left.marginLeftIn === right.marginLeftIn &&
    left.marginBottomIn === right.marginBottomIn &&
    left.marginRightIn === right.marginRightIn &&
    left.lineSpacingPt === right.lineSpacingPt;

  const _findDuplicatePresetName = (
    overrides: RuleOverrides,
    presets: Record<string, CustomPreset>,
    excludeName?: string,
  ) => {
    for (const [name, preset] of Object.entries(presets)) {
      if (excludeName && name === excludeName) {
        continue;
      }
      if (_areOverridesEqual(preset.overrides, overrides)) {
        return name;
      }
    }
    return "";
  };

  const _nextUniquePresetName = (baseName: string, presets: Record<string, CustomPreset>, excludeName?: string) => {
    const trimmedBase = baseName.trim();
    if (!trimmedBase) {
      return "";
    }

    if (!presets[trimmedBase] || trimmedBase === excludeName) {
      return trimmedBase;
    }

    let suffix = 2;
    let candidate = `${trimmedBase} (${suffix})`;
    while (presets[candidate] && candidate !== excludeName) {
      suffix += 1;
      candidate = `${trimmedBase} (${suffix})`;
    }
    return candidate;
  };

  const renameCustomPreset = (oldName: string, requestedName: string) => {
    const trimmed = requestedName.trim();
    if (!trimmed) {
      toast({
        title: "Invalid name",
        description: "Preset name cannot be empty.",
        variant: "destructive",
      });
      return;
    }

    if (trimmed === oldName) {
      setRenamingPresetName("");
      setRenamingPresetDraft("");
      return;
    }

    const resolvedName = _nextUniquePresetName(trimmed, customPresets, oldName);
    const updated = { ...customPresets };
    updated[resolvedName] = updated[oldName];
    delete updated[oldName];

    _persistCustomPresets(updated);

    if (defaultPresetName === oldName) {
      setDefaultPresetName(resolvedName);
      localStorage.setItem("defaultCustomRulePreset", resolvedName);
    }

    if (favoritePresetNames.includes(oldName)) {
      _persistFavoritePresetNames(
        favoritePresetNames.map((item) => (item === oldName ? resolvedName : item))
      );
    }

    setRenamingPresetName("");
    setRenamingPresetDraft("");

    toast({
      title: resolvedName === trimmed ? "Preset renamed" : "Preset renamed with suffix",
      description:
        resolvedName === trimmed
          ? `"${oldName}" is now "${resolvedName}".`
          : `"${trimmed}" already existed, so the preset was saved as "${resolvedName}".`,
    });
  };

  const toggleFavoritePreset = (name: string) => {
    const next = favoritePresetNames.includes(name)
      ? favoritePresetNames.filter((item) => item !== name)
      : [...favoritePresetNames, name];
    _persistFavoritePresetNames(next);
  };

  const _sanitizeOverrideShape = (raw: any): RuleOverrides => ({
    bodyFont: String(raw?.bodyFont ?? ""),
    bodySizePt: String(raw?.bodySizePt ?? ""),
    marginTopIn: String(raw?.marginTopIn ?? ""),
    marginLeftIn: String(raw?.marginLeftIn ?? ""),
    marginBottomIn: String(raw?.marginBottomIn ?? ""),
    marginRightIn: String(raw?.marginRightIn ?? ""),
    lineSpacingPt: String(raw?.lineSpacingPt ?? ""),
  });

  const exportCustomPresets = () => {
    const names = Object.keys(customPresets);
    if (names.length === 0) {
      toast({
        title: "No custom presets",
        description: "Save at least one custom preset before exporting.",
        variant: "destructive",
      });
      return;
    }

    const payload = {
      version: 1,
      exportedAt: new Date().toISOString(),
      defaultPresetName,
      favoritePresetNames,
      presets: customPresets,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const dateStamp = new Date().toISOString().slice(0, 10);
    link.href = url;
    link.download = `docuforage-custom-presets-${dateStamp}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    toast({
      title: "Presets exported",
      description: `${names.length} preset(s) downloaded as JSON.`,
    });
  };

  const _nextUniqueName = (name: string, existing: Record<string, CustomPreset>) => {
    let idx = 2;
    let candidate = `${name} (${idx})`;
    while (existing[candidate]) {
      idx += 1;
      candidate = `${name} (${idx})`;
    }
    return candidate;
  };

  const importCustomPresets = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const source = parsed?.presets && typeof parsed.presets === "object" ? parsed.presets : parsed;
      const importedDefaultPresetName = String(parsed?.defaultPresetName || "").trim();
      const importedFavoritePresetNames = Array.isArray(parsed?.favoritePresetNames)
        ? parsed.favoritePresetNames.map((item: any) => String(item).trim()).filter(Boolean)
        : [];

      if (!source || typeof source !== "object") {
        throw new Error("Invalid preset file format.");
      }

      const normalizedEntries = Object.entries(source)
        .filter(([name]) => Boolean(String(name).trim()))
        .map(([name, value]) => {
          const raw = value && typeof value === "object" && "overrides" in (value as any)
            ? (value as any)
            : { overrides: value, category: "imported", tags: [], createdAt: new Date().toISOString() };
          return [
            String(name).trim(),
            {
              overrides: _sanitizeOverrideShape((raw as any).overrides),
              category: String((raw as any).category ?? "imported"),
              tags: Array.isArray((raw as any).tags)
                ? (raw as any).tags.map((tag: any) => String(tag).trim()).filter(Boolean)
                : [],
              createdAt: String((raw as any).createdAt ?? new Date().toISOString()),
            } satisfies CustomPreset,
          ] as const;
        });

      if (normalizedEntries.length === 0) {
        throw new Error("No valid presets found in file.");
      }

      const merged: Record<string, CustomPreset> = { ...customPresets };
      let importedCount = 0;
      let skippedCount = 0;
      let overwrittenCount = 0;
      let renamedCount = 0;

      for (const [name, preset] of normalizedEntries) {
        if (!merged[name]) {
          merged[name] = preset;
          importedCount += 1;
          continue;
        }

        if (importConflictStrategy === "skip") {
          skippedCount += 1;
          continue;
        }

        if (importConflictStrategy === "overwrite") {
          merged[name] = preset;
          overwrittenCount += 1;
          continue;
        }

        const renamed = _nextUniqueName(name, merged);
        merged[renamed] = preset;
        renamedCount += 1;
      }

      _persistCustomPresets(merged);
      if (importedDefaultPresetName && merged[importedDefaultPresetName] && !defaultPresetName) {
        setDefaultPresetName(importedDefaultPresetName);
        localStorage.setItem("defaultCustomRulePreset", importedDefaultPresetName);
      }
      if (importedFavoritePresetNames.length > 0) {
        const mergedFavorites = Array.from(
          new Set(
            [...favoritePresetNames, ...importedFavoritePresetNames].filter((name) => Boolean(merged[name]))
          )
        );
        _persistFavoritePresetNames(mergedFavorites);
      }

      toast({
        title: "Presets imported",
        description: `${importedCount} added, ${overwrittenCount} overwritten, ${renamedCount} renamed, ${skippedCount} skipped.`,
      });
    } catch (err: any) {
      toast({
        title: "Import failed",
        description: err?.message || "Could not import preset file.",
        variant: "destructive",
      });
    } finally {
      event.target.value = "";
    }
  };

  const deleteCustomPreset = (name: string) => {
    const updated = { ...customPresets };
    delete updated[name];
    _persistCustomPresets(updated);
    if (defaultPresetName === name) {
      setDefaultPresetName("");
      localStorage.removeItem("defaultCustomRulePreset");
    }
    if (favoritePresetNames.includes(name)) {
      _persistFavoritePresetNames(favoritePresetNames.filter((item) => item !== name));
    }
    if (renamingPresetName === name) {
      setRenamingPresetName("");
      setRenamingPresetDraft("");
    }

    toast({
      title: "Preset deleted",
      description: `"${name}" has been removed.`,
    });
  };

  type RulePreset = {
    label: string;
    description: string;
    overrides: Partial<typeof ruleOverrides>;
  };

  const RULE_PRESETS: Record<string, RulePreset> = {
    academic: {
      label: "Academic",
      description: "Double spacing, Times New Roman 12pt, 1\" margins",
      overrides: {
        bodyFont: "Times New Roman",
        bodySizePt: "12",
        marginTopIn: "1.0",
        marginLeftIn: "1.0",
        marginBottomIn: "1.0",
        marginRightIn: "1.0",
        lineSpacingPt: "24.0",
      },
    },
    formal: {
      label: "Formal Business",
      description: "Calibri 11pt, 0.75\" margins, 1.5x spacing",
      overrides: {
        bodyFont: "Calibri",
        bodySizePt: "11",
        marginTopIn: "0.75",
        marginLeftIn: "0.75",
        marginBottomIn: "0.75",
        marginRightIn: "0.75",
        lineSpacingPt: "16.5",
      },
    },
    compact: {
      label: "Compact",
      description: "Arial 10pt, 0.5\" margins, single spacing",
      overrides: {
        bodyFont: "Arial",
        bodySizePt: "10",
        marginTopIn: "0.5",
        marginLeftIn: "0.5",
        marginBottomIn: "0.5",
        marginRightIn: "0.5",
        lineSpacingPt: "12.0",
      },
    },
    generous: {
      label: "Generous Spacing",
      description: "Calibri 12pt, 1.5\" margins, double spacing",
      overrides: {
        bodyFont: "Calibri",
        bodySizePt: "12",
        marginTopIn: "1.5",
        marginLeftIn: "1.5",
        marginBottomIn: "1.5",
        marginRightIn: "1.5",
        lineSpacingPt: "24.0",
      },
    },
    minimal: {
      label: "Minimal",
      description: "Courier 10pt, 0.25\" margins, single spacing",
      overrides: {
        bodyFont: "Courier",
        bodySizePt: "10",
        marginTopIn: "0.25",
        marginLeftIn: "0.25",
        marginBottomIn: "0.25",
        marginRightIn: "0.25",
        lineSpacingPt: "12.0",
      },
    },
  };

  const applyPreset = (presetKey: string) => {
    const preset = RULE_PRESETS[presetKey];
    if (preset) {
      setRuleOverrides((prev) => ({
        ...prev,
        ...preset.overrides,
      }));
      toast({
        title: `"${preset.label}" preset applied`,
        description: preset.description,
      });
    }
  };

  const clearOverrides = () => {
    setRuleOverrides({
      bodyFont: "",
      bodySizePt: "",
      marginTopIn: "",
      marginLeftIn: "",
      marginBottomIn: "",
      marginRightIn: "",
      lineSpacingPt: "",
    });
    toast({
      title: "Overrides cleared",
      description: "All overrides have been reset to defaults.",
    });
  };

  const presetCategories = Array.from(
    new Set(Object.values(customPresets).map((preset) => preset.category || "general"))
  ).sort((a, b) => a.localeCompare(b));

  const filteredCustomPresetEntries = Object.entries(customPresets)
    .filter(([name, preset]) => {
      const query = presetSearchTerm.trim().toLowerCase();
      const haystack = `${name} ${(preset.category || "")} ${(preset.tags || []).join(" ")}`.toLowerCase();
      const matchesQuery = !query || haystack.includes(query);

      const matchesCategory =
        presetCategoryFilter === "all"
          ? true
          : presetCategoryFilter === "favorites"
            ? favoritePresetNames.includes(name)
            : (preset.category || "general") === presetCategoryFilter;

      return matchesQuery && matchesCategory;
    })
    .sort(([nameA], [nameB]) => {
      const favA = favoritePresetNames.includes(nameA);
      const favB = favoritePresetNames.includes(nameB);
      if (favA !== favB) return favA ? -1 : 1;
      if (nameA === defaultPresetName) return -1;
      if (nameB === defaultPresetName) return 1;
      return nameA.localeCompare(nameB);
    });

  const addSection = () => {
    const newId = String(Date.now());
    setSections([
      ...sections,
      { id: newId, title: `Section ${sections.length + 1}`, mode: "auto_generate" as const },
    ]);
  };

  const removeSection = (id: string) => {
    setSections(sections.filter((s) => s.id !== id));
  };

  const updateSection = (id: string, updates: Partial<DocumentSection>) => {
    setSections(
      sections.map((s) => (s.id === id ? { ...s, ...updates } : s))
    );
  };

  const moveSection = (id: string, direction: "up" | "down") => {
    const idx = sections.findIndex((s) => s.id === id);
    if ((direction === "up" && idx === 0) || (direction === "down" && idx === sections.length - 1)) return;
    const newSections = [...sections];
    const swapIdx = direction === "up" ? idx - 1 : idx + 1;
    [newSections[idx], newSections[swapIdx]] = [newSections[swapIdx], newSections[idx]];
    setSections(newSections);
  };

  const extractRules = async () => {
    if (!styleReferenceFile) {
      toast({
        title: "Select a DOCX file",
        description: "Choose a reference DOCX to extract formatting rules.",
        variant: "destructive",
      });
      return;
    }

    if (!styleReferenceFile.name.toLowerCase().endsWith(".docx")) {
      toast({
        title: "Invalid file type",
        description: "Please upload a .docx reference document.",
        variant: "destructive",
      });
      return;
    }

    setExtractingRules(true);
    try {
      const extracted = await extractRulesFromDocx({
        file: styleReferenceFile,
        documentType: ruleDocumentType,
        notes: ruleNotes || "Extracted from Create Report UI",
      });

      setRulesId(extracted.rules_id || "");
      setRuleValidationWarnings(extracted.validation?.warnings || []);
      const summary = extracted.rules_summary;
      const text = summary
        ? `${summary.body_font || "N/A"}, ${summary.body_size || "N/A"}, confidence: ${summary.confidence || "N/A"}`
        : "Rules extracted";
      setRulesSummary(text);

      toast({
        title: "Rules extracted",
        description: `rules_id: ${extracted.rules_id}`,
      });
    } catch (err: any) {
      toast({
        title: "Extraction failed",
        description: err?.message || "Could not extract rules from document.",
        variant: "destructive",
      });
    } finally {
      setExtractingRules(false);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;
    if (content.length > MAX_CONTENT) {
      toast({
        title: "Content too large",
        description: `Please keep content under ${MAX_CONTENT.toLocaleString()} characters.`,
        variant: "destructive",
      });
      return;
    }

    const allFiles = [...contentFiles, ...referenceFiles];
    const oversized = allFiles.find((f) => f.size > MAX_FILE_BYTES);
    if (oversized) {
      toast({
        title: "File too large",
        description: `${oversized.name} exceeds ${Math.floor(MAX_FILE_BYTES / 1_000_000)}MB limit.`,
        variant: "destructive",
      });
      return;
    }

    setBusy(true);
    try {
      const contentFilePayloads = await Promise.all(
        contentFiles.map(async (file) => ({
          filename: file.name,
          mimeType: file.type || "application/octet-stream",
          contentBase64: await fileToBase64(file),
          role: "content" as const,
        }))
      );
      const referenceFilePayloads = await Promise.all(
        referenceFiles.map(async (file) => ({
          filename: file.name,
          mimeType: file.type || "application/octet-stream",
          contentBase64: await fileToBase64(file),
          role: "reference" as const,
        }))
      );

      const metadataPayload = metadataFields.reduce<Record<string, string>>((acc, field) => {
        const key = field.key.trim();
        if (!key) {
          return acc;
        }
        acc[key] = field.value;
        return acc;
      }, {});

      const response = await generateReport({
        userId: user.uid,
        title,
        rules,
        rulesId: rulesId || undefined,
        content,
        referenceContent,
        referenceMimeType: "text/plain",
        inputFiles: [...contentFilePayloads, ...referenceFilePayloads],
        metadata: Object.keys(metadataPayload).length > 0 ? metadataPayload : undefined,
        sections: sections.map((s) => ({
          title: s.title,
          mode: s.mode,
        })),
        ruleOverrides: Object.fromEntries(
          Object.entries(ruleOverrides).filter(([, v]) => v !== "")
        ),
      });

      if (!response.reportId) {
        throw new Error("Backend did not return a report ID.");
      }

      navigate(`/reports/${response.reportId}`);

      if (response.status === "failed") {
        toast({
          title: "Backend error",
          description: response.error ?? "Generation failed.",
          variant: "destructive",
        });
      }
    } catch (err: any) {
      const apiError = err instanceof ApiError ? err : null;
      if (apiError?.reportId) {
        navigate(`/reports/${apiError.reportId}`);
      }

      const qualityDetails = apiError?.qualityErrors?.length
        ? ` ${apiError.qualityErrors.join("; ")}`
        : "";
      toast({
        title: "Report generation failed",
        description: `${err?.message ?? "Could not reach the backend."}${qualityDetails}`,
        variant: "destructive",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppShell>
      <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-4">
        <ArrowLeft className="mr-2 h-4 w-4" /> Back
      </Button>

      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Create Report</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Describe formatting rules and paste your raw content. DocuForge AI compiles a structured PDF & DOCX.
        </p>
      </div>

      <Card className="gradient-card border-border/60 shadow-card">
        <CardContent className="p-6">
          <form onSubmit={submit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. The Impact of AI on Modern Education"
              />
            </div>

            <div className="space-y-3 rounded-md border border-border/60 p-4">
              <div className="space-y-2">
                <Label htmlFor="styleReference">Reference DOCX for Style Extraction (optional)</Label>
                <Input
                  id="styleReference"
                  type="file"
                  accept=".docx"
                  onChange={(e) => {
                    setStyleReferenceFile(e.target.files?.[0] || null);
                    setRulesId("");
                    setRulesSummary("");
                    setRuleValidationWarnings([]);
                  }}
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="ruleDocumentType">Document Type</Label>
                  <Input
                    id="ruleDocumentType"
                    value={ruleDocumentType}
                    onChange={(e) => setRuleDocumentType(e.target.value || "generic")}
                    placeholder="e.g. business, academic, legal"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="ruleNotes">Extraction Notes</Label>
                  <Input
                    id="ruleNotes"
                    value={ruleNotes}
                    onChange={(e) => setRuleNotes(e.target.value)}
                    placeholder="Optional note for this extracted rule set"
                  />
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  type="button"
                  variant="outline"
                  onClick={extractRules}
                  disabled={extractingRules || !styleReferenceFile}
                >
                  {extractingRules ? "Extracting Rules..." : "Extract Rules"}
                </Button>
                {rulesId ? <span className="text-xs text-muted-foreground">rules_id: {rulesId}</span> : null}
              </div>
              {rulesSummary ? <p className="text-xs text-muted-foreground">{rulesSummary}</p> : null}
              {ruleValidationWarnings.length > 0 ? (
                <div className="rounded-md border border-amber-300/60 bg-amber-50/60 p-3 text-xs text-amber-900">
                  <p className="font-medium">Rule validation warnings</p>
                  <ul className="mt-2 list-disc space-y-1 pl-4">
                    {ruleValidationWarnings.map((item, idx) => (
                      <li key={`${item}-${idx}`}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="rules">Formatting Rules</Label>
              <Textarea
                id="rules"
                required
                rows={5}
                value={rules}
                onChange={(e) => setRules(e.target.value)}
                placeholder="Describe sections, tone, citation style, formatting requirements…"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="reference">Optional Reference Content</Label>
              <Textarea
                id="reference"
                rows={5}
                value={referenceContent}
                onChange={(e) => setReferenceContent(e.target.value)}
                placeholder="Optional: paste a sample structure you want to mimic (organization only, not wording)."
              />
            </div>

            <div className="space-y-3 rounded-md border border-border/60 bg-secondary/20 p-4">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-sm">Document Metadata</h3>
                <span className="text-xs text-muted-foreground">(key/value fields that appear on the cover page)</span>
              </div>
              <ScrollArea className="h-72 rounded-md border border-border/40 bg-background/60">
                <div className="space-y-2 p-3 pr-4">
                  {metadataFields.map((field, index) => (
                    <div key={field.id} className="grid gap-2 rounded-md border border-border/40 bg-background/70 p-3 md:grid-cols-[1fr_1.5fr_auto] md:items-end">
                      <div className="space-y-2">
                        <Label htmlFor={`metadata-key-${field.id}`}>Field name</Label>
                        <Input
                          id={`metadata-key-${field.id}`}
                          value={field.key}
                          onChange={(e) => updateMetadataField(field.id, { key: e.target.value })}
                          placeholder={index === 0 ? "author" : "custom_field"}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor={`metadata-value-${field.id}`}>Value</Label>
                        <Input
                          id={`metadata-value-${field.id}`}
                          value={field.value}
                          onChange={(e) => updateMetadataField(field.id, { value: e.target.value })}
                          placeholder={index === 0 ? "John Smith" : "Enter metadata value"}
                        />
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => removeMetadataField(field.id)}
                        className="h-9 w-full md:w-auto"
                        disabled={metadataFields.length <= 1}
                      >
                        <Trash2 className="mr-1 h-3.5 w-3.5" /> Remove
                      </Button>
                    </div>
                  ))}
                </div>
              </ScrollArea>
              <div className="flex flex-wrap items-center gap-2">
                <Button type="button" variant="outline" size="sm" onClick={addMetadataField} className="h-8">
                  <Plus className="mr-1 h-3 w-3" /> Add Metadata Field
                </Button>
                <p className="text-xs text-muted-foreground">
                  Use any field names you need. Empty field names are skipped during submission.
                </p>
              </div>
            </div>

            <div className="space-y-3 rounded-md border border-border/60 bg-secondary/20 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-sm">Document Sections</h3>
                  <span className="text-xs text-muted-foreground">(define structure and generation mode)</span>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={addSection}
                  className="h-8"
                >
                  <Plus className="mr-1 h-3 w-3" /> Add Section
                </Button>
              </div>
              <ScrollArea className="h-64 rounded-md border border-border/40 bg-background/60">
                <div className="space-y-2 p-2 pr-3">
                  {sections.map((section, idx) => (
                    <div key={section.id} className="flex items-center gap-2 rounded bg-background p-2 border border-border/40">
                      <GripVertical className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                      <Input
                        type="text"
                        value={section.title}
                        onChange={(e) => updateSection(section.id, { title: e.target.value })}
                        placeholder="Section title"
                        className="h-8 flex-1"
                      />
                      <Select
                        value={section.mode}
                        onValueChange={(value) =>
                          updateSection(section.id, {
                            mode: value as DocumentSection["mode"],
                          })
                        }
                      >
                        <SelectTrigger className="h-8 w-[11rem] flex-shrink-0 text-xs sm:w-[12rem]">
                          <SelectValue placeholder="Choose mode" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="auto_generate">AI Generate</SelectItem>
                          <SelectItem value="user_provides">User Content</SelectItem>
                          <SelectItem value="skip">Skip</SelectItem>
                        </SelectContent>
                      </Select>
                      <div className="flex flex-shrink-0 gap-1">
                        <button
                          type="button"
                          onClick={() => moveSection(section.id, "up")}
                          disabled={idx === 0}
                          className="rounded p-1 hover:bg-secondary disabled:opacity-30"
                          title="Move up"
                        >
                          <ChevronUp className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => moveSection(section.id, "down")}
                          disabled={idx === sections.length - 1}
                          className="rounded p-1 hover:bg-secondary disabled:opacity-30"
                          title="Move down"
                        >
                          <ChevronDown className="h-4 w-4" />
                        </button>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeSection(section.id)}
                        disabled={sections.length <= 1}
                        className="flex-shrink-0 rounded p-1 text-destructive hover:bg-destructive/10 disabled:opacity-30"
                        title="Delete section"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </ScrollArea>
              <p className="text-xs text-muted-foreground">
                Sections define the document structure. "AI Generate" uses your content and rules. "User Content" expects you to provide text. "Skip" omits the section.
              </p>

              {sections.length > 0 && (
                <div className="space-y-2 pt-3 border-t border-border/40">
                  <p className="text-xs font-medium text-muted-foreground">Generation Preview:</p>
                  <div className="space-y-1">
                    {sections.map((section) => (
                      <div key={section.id} className="flex gap-2 items-start text-xs">
                        {section.mode === "auto_generate" && (
                          <>
                            <span className="text-emerald-600 font-bold">✓</span>
                            <span className="text-muted-foreground">
                              <strong>{section.title}</strong> – AI will generate content using your rules and input.
                            </span>
                          </>
                        )}
                        {section.mode === "user_provides" && (
                          <>
                            <span className="text-blue-600 font-bold">📝</span>
                            <span className="text-muted-foreground">
                              <strong>{section.title}</strong> – Heading included; you provide the content.
                            </span>
                          </>
                        )}
                        {section.mode === "skip" && (
                          <>
                            <span className="text-gray-400 font-bold">⊘</span>
                            <span className="text-gray-400">
                              <strong>{section.title}</strong> – This section will be omitted from output.
                            </span>
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {rulesId && (
              <div className="space-y-3 rounded-md border border-border/60 bg-blue-500/5 p-4">
                <button
                  type="button"
                  onClick={() => setShowRuleOverrides(!showRuleOverrides)}
                  className="flex w-full items-center justify-between font-semibold text-sm hover:opacity-80"
                >
                  <span>⚙️ Rule Overrides (Optional)</span>
                  <span className="text-xs text-muted-foreground">{showRuleOverrides ? "▼" : "▶"}</span>
                </button>
                {showRuleOverrides && (
                  <div className="space-y-3 pt-2 border-t border-border/40">
                    <p className="text-xs text-muted-foreground">
                      Override formatting rules from "{ruleDocumentType}". Leave empty to use extracted values.
                    </p>

                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-medium text-muted-foreground">Quick Presets:</p>
                        <div className="flex items-center gap-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={exportCustomPresets}
                            className="h-6 px-2 text-xs"
                            title="Export custom presets to JSON"
                          >
                            Export
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => presetImportInputRef.current?.click()}
                            className="h-6 px-2 text-xs"
                            title="Import presets from JSON"
                          >
                            Import
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => setShowSavePreset(!showSavePreset)}
                            className="h-6 px-2 text-xs"
                            title="Save current overrides as a custom preset"
                          >
                            Save as Preset
                          </Button>
                        </div>
                      </div>

                      <Input
                        ref={presetImportInputRef}
                        type="file"
                        accept="application/json,.json"
                        onChange={importCustomPresets}
                        className="hidden"
                      />

                      {showSavePreset && (
                        <div className="space-y-2 p-2 rounded bg-muted/50 border border-border/50">
                                          <div className="flex gap-2">
                            <Input
                              type="text"
                              value={newPresetName}
                              onChange={(e) => setNewPresetName(e.target.value)}
                              placeholder="Preset name (e.g., 'My Standard')"
                              className="h-7 text-xs flex-1"
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  saveCustomPreset(newPresetName);
                                }
                              }}
                            />
                            <Button
                              type="button"
                              variant="default"
                              size="sm"
                              onClick={() => saveCustomPreset(newPresetName)}
                              className="h-7 px-2 text-xs"
                            >
                              Save
                            </Button>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setShowSavePreset(false);
                                setNewPresetName("");
                              }}
                              className="h-7 px-2 text-xs"
                            >
                              Cancel
                            </Button>
                          </div>
                          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                            <Input
                              type="text"
                              value={newPresetCategory}
                              onChange={(e) => setNewPresetCategory(e.target.value)}
                              placeholder="Category (e.g., academic)"
                              className="h-7 text-xs"
                            />
                            <Input
                              type="text"
                              value={newPresetTags}
                              onChange={(e) => setNewPresetTags(e.target.value)}
                              placeholder="Tags comma-separated"
                              className="h-7 text-xs"
                            />
                          </div>
                        </div>
                      )}

                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span>On import conflicts:</span>
                        <Select
                          value={importConflictStrategy}
                          onValueChange={(value) => setImportConflictStrategy(value as "overwrite" | "skip" | "rename")}
                        >
                          <SelectTrigger className="h-7 w-44 text-xs">
                            <SelectValue placeholder="Choose conflict strategy" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="rename">Rename incoming</SelectItem>
                            <SelectItem value="overwrite">Overwrite existing</SelectItem>
                            <SelectItem value="skip">Skip incoming</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                        {Object.entries(RULE_PRESETS).map(([key, preset]) => (
                          <Button
                            key={key}
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => applyPreset(key)}
                            className="h-8 text-xs justify-start"
                            title={preset.description}
                          >
                            {preset.label}
                          </Button>
                        ))}
                      </div>

                      {Object.keys(customPresets).length > 0 && (
                        <div className="space-y-2">
                          <p className="text-xs font-medium text-muted-foreground">Your Presets:</p>

                          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                            <Input
                              type="text"
                              value={presetSearchTerm}
                              onChange={(e) => setPresetSearchTerm(e.target.value)}
                              placeholder="Search by name, category, or tag"
                              className="h-7 text-xs"
                            />
                            <select
                              value={presetCategoryFilter}
                              onChange={(e) => setPresetCategoryFilter(e.target.value)}
                              className="h-7 rounded border border-input bg-background px-2 text-xs"
                            >
                              <option value="all">All categories</option>
                              <option value="favorites">Favorites</option>
                              {presetCategories.map((category) => (
                                <option key={category} value={category}>
                                  {category}
                                </option>
                              ))}
                            </select>
                          </div>

                          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                            {filteredCustomPresetEntries.map(([name, preset]) => (
                              <div
                                key={name}
                                className="relative rounded border border-border/60 bg-background/70 p-2"
                              >
                                {renamingPresetName === name ? (
                                  <div className="space-y-2">
                                    <Input
                                      type="text"
                                      value={renamingPresetDraft}
                                      onChange={(e) => setRenamingPresetDraft(e.target.value)}
                                      placeholder="Rename preset"
                                      className="h-8 text-xs"
                                      autoFocus
                                      onKeyDown={(e) => {
                                        if (e.key === "Enter") {
                                          renameCustomPreset(name, renamingPresetDraft);
                                        }
                                        if (e.key === "Escape") {
                                          setRenamingPresetName("");
                                          setRenamingPresetDraft("");
                                        }
                                      }}
                                    />
                                    <div className="flex items-center gap-2">
                                      <Button
                                        type="button"
                                        variant="default"
                                        size="sm"
                                        onClick={() => renameCustomPreset(name, renamingPresetDraft)}
                                        className="h-7 px-2 text-xs"
                                      >
                                        Save
                                      </Button>
                                      <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        onClick={() => {
                                          setRenamingPresetName("");
                                          setRenamingPresetDraft("");
                                        }}
                                        className="h-7 px-2 text-xs"
                                      >
                                        Cancel
                                      </Button>
                                    </div>
                                  </div>
                                ) : (
                                  <>
                                    <Button
                                      type="button"
                                      variant="secondary"
                                      size="sm"
                                      onClick={() => {
                                        setRuleOverrides(preset.overrides);
                                        toast({
                                          title: "Custom preset applied",
                                          description: `"${name}" has been loaded.`,
                                        });
                                      }}
                                      className="h-8 text-xs justify-start w-full pr-32"
                                      title={`Load custom preset: ${name} (${preset.category})`}
                                    >
                                      {favoritePresetNames.includes(name) ? "★ " : ""}
                                      {name}
                                      {defaultPresetName === name ? " *" : ""}
                                    </Button>

                                    <div className="absolute right-2 top-2 flex items-center gap-1">
                                      <button
                                        type="button"
                                        onClick={() => toggleFavoritePreset(name)}
                                        className="rounded p-1 text-amber-600 hover:bg-amber-100"
                                        title={favoritePresetNames.includes(name) ? "Remove from favorites" : "Add to favorites"}
                                      >
                                        {favoritePresetNames.includes(name) ? "★" : "☆"}
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => {
                                          setDefaultPresetName(name);
                                          localStorage.setItem("defaultCustomRulePreset", name);
                                          toast({
                                            title: "Default preset set",
                                            description: `"${name}" will be marked as your default.`,
                                          });
                                        }}
                                        className="rounded p-1 text-blue-600 hover:bg-blue-100"
                                        title="Set as default preset"
                                      >
                                        D
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => {
                                          setRenamingPresetName(name);
                                          setRenamingPresetDraft(name);
                                        }}
                                        className="rounded p-1 text-foreground hover:bg-secondary"
                                        title="Rename this preset"
                                      >
                                        R
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => deleteCustomPreset(name)}
                                        className="rounded p-1 text-destructive hover:bg-destructive/10"
                                        title="Delete this preset"
                                      >
                                        ✕
                                      </button>
                                    </div>

                                    <p className="mt-2 text-[11px] text-muted-foreground">
                                      {preset.category}
                                      {preset.tags.length > 0 ? ` • ${preset.tags.join(", ")}` : ""}
                                    </p>
                                  </>
                                )}
                              </div>
                            ))}
                          </div>

                          {filteredCustomPresetEntries.length === 0 && (
                            <p className="text-xs text-muted-foreground">No presets match your current filters.</p>
                          )}

                          <p className="text-[11px] text-muted-foreground">* Marks your default preset, ★ marks favorite presets</p>
                        </div>
                      )}

                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={clearOverrides}
                        className="h-7 text-xs w-full text-muted-foreground hover:text-foreground"
                      >
                        Clear all
                      </Button>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-1">
                        <Label htmlFor="bodyFont" className="text-xs">Font (e.g., Calibri)</Label>
                        <Input
                          id="bodyFont"
                          value={ruleOverrides.bodyFont}
                          onChange={(e) => setRuleOverrides({ ...ruleOverrides, bodyFont: e.target.value })}
                          placeholder="Font family"
                          className="h-8 text-sm"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="bodySizePt" className="text-xs">Size (pt)</Label>
                        <Input
                          id="bodySizePt"
                          type="number"
                          value={ruleOverrides.bodySizePt}
                          onChange={(e) => setRuleOverrides({ ...ruleOverrides, bodySizePt: e.target.value })}
                          placeholder="12"
                          className="h-8 text-sm"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="marginTopIn" className="text-xs">Top Margin (in)</Label>
                        <Input
                          id="marginTopIn"
                          type="number"
                          step="0.1"
                          value={ruleOverrides.marginTopIn}
                          onChange={(e) => setRuleOverrides({ ...ruleOverrides, marginTopIn: e.target.value })}
                          placeholder="1.0"
                          className="h-8 text-sm"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="marginLeftIn" className="text-xs">Left Margin (in)</Label>
                        <Input
                          id="marginLeftIn"
                          type="number"
                          step="0.1"
                          value={ruleOverrides.marginLeftIn}
                          onChange={(e) => setRuleOverrides({ ...ruleOverrides, marginLeftIn: e.target.value })}
                          placeholder="1.0"
                          className="h-8 text-sm"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="marginBottomIn" className="text-xs">Bottom Margin (in)</Label>
                        <Input
                          id="marginBottomIn"
                          type="number"
                          step="0.1"
                          value={ruleOverrides.marginBottomIn}
                          onChange={(e) => setRuleOverrides({ ...ruleOverrides, marginBottomIn: e.target.value })}
                          placeholder="1.0"
                          className="h-8 text-sm"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="marginRightIn" className="text-xs">Right Margin (in)</Label>
                        <Input
                          id="marginRightIn"
                          type="number"
                          step="0.1"
                          value={ruleOverrides.marginRightIn}
                          onChange={(e) => setRuleOverrides({ ...ruleOverrides, marginRightIn: e.target.value })}
                          placeholder="1.0"
                          className="h-8 text-sm"
                        />
                      </div>
                      <div className="space-y-1 sm:col-span-2">
                        <Label htmlFor="lineSpacingPt" className="text-xs">Line Spacing (pt)</Label>
                        <Input
                          id="lineSpacingPt"
                          type="number"
                          step="0.1"
                          value={ruleOverrides.lineSpacingPt}
                          onChange={(e) => setRuleOverrides({ ...ruleOverrides, lineSpacingPt: e.target.value })}
                          placeholder="14.0"
                          className="h-8 text-sm"
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="contentFiles">Content Files (optional)</Label>
                <Input
                  id="contentFiles"
                  type="file"
                  multiple
                  accept="*/*"
                  onChange={(e) => setContentFiles(Array.from(e.target.files || []))}
                />
                <p className="text-xs text-muted-foreground">
                  Accepted: text, JSON, CSV, DOCX, PDF, images, and other files. Unsupported binary files are kept as metadata.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="referenceFiles">Reference Files (optional)</Label>
                <Input
                  id="referenceFiles"
                  type="file"
                  multiple
                  accept="*/*"
                  onChange={(e) => setReferenceFiles(Array.from(e.target.files || []))}
                />
                <p className="text-xs text-muted-foreground">Use this to align output structure with sample documents.</p>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="content">Content</Label>
                <span className={`text-xs ${content.length > MAX_CONTENT ? "text-destructive" : "text-muted-foreground"}`}>
                  {content.length.toLocaleString()} / {MAX_CONTENT.toLocaleString()}
                </span>
              </div>
              <Textarea
                id="content"
                rows={14}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Paste raw notes, sources, data, or a draft. The AI will structure it according to your rules."
                className="font-mono text-sm"
              />
            </div>

            <Button
              type="submit"
              disabled={busy}
              className="w-full gradient-primary text-primary-foreground hover:opacity-90"
            >
              <Sparkles className="mr-2 h-4 w-4" />
              {busy ? "Generating…" : "Generate Report"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </AppShell>
  );
}
