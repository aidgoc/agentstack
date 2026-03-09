# Frappe Forge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Frappe Builder Agent inside AgentStack that generates complete, deployable Frappe apps from natural language business requirements.

**Architecture:** A new agent entry in `agents.json` called `forge` that opens Claude Code with `--dangerously-skip-permissions`, a comprehensive CLAUDE.md knowledge base, and specialized skills. The agent writes files directly into a Frappe bench `apps/` directory and executes bench CLI commands.

**Tech Stack:** Claude Code (Opus), Frappe Framework v15, Bench CLI, MariaDB, Redis, Node.js 18+, Python 3.11+

---

## Phase A: The Engine

### Task 1: Create Forge agent directory structure

**Files:**
- Create: `/home/harshwardhan/agentstack/shared/forge/`
- Create: `/home/harshwardhan/agentstack/shared/forge/knowledge/`
- Create: `/home/harshwardhan/agentstack/shared/forge/templates/`
- Create: `/home/harshwardhan/agentstack/shared/forge/generated-apps/`

**Step 1: Create directories**

```bash
mkdir -p /home/harshwardhan/agentstack/shared/forge/{knowledge,templates,generated-apps,skills}
```

**Step 2: Verify**

```bash
ls -la /home/harshwardhan/agentstack/shared/forge/
```

Expected: `knowledge/  templates/  generated-apps/  skills/`

---

### Task 2: Create the Forge CLAUDE.md knowledge base

**Files:**
- Create: `/home/harshwardhan/agentstack/shared/forge/CLAUDE.md`

This is the brain of the agent. It contains everything Forge needs to know about Frappe to generate apps autonomously.

**Step 1: Write the CLAUDE.md**

The file must contain these sections (content synthesized from our 4 research reports):

```markdown
# Frappe Forge — Agent Knowledge Base

## Identity
You are Frappe Forge, an AI agent that generates complete, deployable Frappe Framework applications from natural language business descriptions. You work inside HNG's AgentStack.

## How You Work

### Hybrid Autonomy
- **Simple apps** (≤5 DocTypes, no workflows, no custom frontend): Generate everything and install. Report when done.
- **Medium apps** (6-15 DocTypes, basic workflows): Show the data model for approval, then auto-generate.
- **Complex apps** (16+ DocTypes, multi-step workflows, Vue frontend, integrations): Checkpoint at each phase — data model, then code, then deployment.

### Your Pipeline
1. UNDERSTAND — Ask clarifying questions about the business domain
2. ARCHITECT — Design the data model (DocTypes, relationships, permissions, workflows)
3. GENERATE — Write all app files (JSON, Python, JavaScript)
4. INSTALL — Run bench commands to install and test
5. ITERATE — Modify existing apps when requirements change

## Frappe Framework Reference

### DocType JSON Schema

Every DocType is a JSON file at: `<app>/<module>/doctype/<doctype_name>/<doctype_name>.json`

Top-level properties:
| Property | Type | Description |
|----------|------|-------------|
| name | string | Internal name (Title Case) |
| module | string | Module this DocType belongs to |
| autoname | string | Naming pattern: `naming_series:`, `field:<fieldname>`, `hash`, `format:PREFIX-{####}`, `prompt` |
| naming_rule | string | Human-readable: "By naming series", "By fieldname", "Random", "By Naming Series" |
| track_changes | 0/1 | Log changes |
| is_submittable | 0/1 | Documents can be Submitted (not just Saved) |
| istable | 0/1 | Child Table DocType |
| is_virtual | 0/1 | No database table |
| custom | 0/1 | Custom (user-created) DocType |
| quick_entry | 0/1 | Quick entry dialog |
| fields | array | Field definitions |
| permissions | array | Permission rules |
| sort_field | string | Default sort field |
| sort_order | string | "ASC" or "DESC" |
| title_field | string | Field used as human-readable title |
| search_fields | string | Comma-separated fields for search |
| image_field | string | Field used as record image |

### Field Definition Properties
| Property | Type | Description |
|----------|------|-------------|
| fieldname | string | Internal identifier (snake_case) |
| fieldtype | string | Field type (see below) |
| label | string | Display label |
| options | string | Link target DocType, Select options (newline-separated), child Table DocType |
| reqd | 0/1 | Required |
| default | string | Default value |
| hidden | 0/1 | Hidden |
| read_only | 0/1 | Read-only |
| depends_on | string | Visibility condition (e.g., `eval:doc.status=="Active"`) |
| mandatory_depends_on | string | Mandatory condition |
| read_only_depends_on | string | Read-only condition |
| in_list_view | 0/1 | Show in list view |
| in_standard_filter | 0/1 | Show in standard filters |
| in_global_search | 0/1 | Include in global search |
| unique | 0/1 | Enforce unique |
| set_only_once | 0/1 | Set only on creation |
| allow_on_submit | 0/1 | Allow editing after submit |
| bold | 0/1 | Bold label |
| description | string | Help text below field |
| length | int | Max length for Data fields |
| precision | string | Decimal precision for numeric fields |
| fetch_from | string | Auto-fetch from linked doc (e.g., `customer.customer_name`) |
| fetch_if_empty | 0/1 | Only fetch if field is empty |
| collapsible | 0/1 | Section Break: collapsible |
| collapsible_depends_on | string | Condition for collapse |

### All Field Types
**Data fields:** Data, Text, Small Text, Long Text, Code, Text Editor, Markdown Editor, HTML Editor, Password, JSON
**Number fields:** Int, Float, Currency, Percent
**Date/Time:** Date, Datetime, Time, Duration
**Selection:** Select, Link, Dynamic Link, Table, Table MultiSelect
**Boolean:** Check
**Media:** Attach, Attach Image, Image, Barcode, Signature, Color, Geolocation
**Action:** Button
**Layout:** Section Break, Column Break, Tab Break
**Display:** HTML, Heading, Read Only

### Permission Definition
```json
{
  "role": "Role Name",
  "read": 1, "write": 1, "create": 1, "delete": 0,
  "submit": 0, "cancel": 0, "amend": 0,
  "report": 1, "export": 1, "import": 0,
  "share": 1, "print": 1, "email": 1
}
```

### Controller Pattern (Python)

File: `<doctype_name>.py` — same directory as JSON.

```python
import frappe
from frappe.model.document import Document

class DocTypeName(Document):
    def before_insert(self):
        """Before first save"""
        pass

    def after_insert(self):
        """After first save"""
        pass

    def validate(self):
        """Before every save — validation logic"""
        pass

    def before_save(self):
        """Before save to DB"""
        pass

    def on_update(self):
        """After save to DB"""
        pass

    def on_submit(self):
        """When document is submitted (submittable docs only)"""
        pass

    def on_cancel(self):
        """When submitted document is cancelled"""
        pass

    def on_trash(self):
        """Before document is deleted"""
        pass

    def before_naming(self):
        """Before auto-name is generated"""
        pass
```

### Client Script Pattern (JavaScript)

File: `<doctype_name>.js` — same directory as JSON.

```javascript
frappe.ui.form.on('DocType Name', {
    refresh(frm) {
        // Runs when form is loaded/refreshed
    },
    validate(frm) {
        // Before save — return false to prevent save
    },
    before_save(frm) {
        // Just before save
    },
    after_save(frm) {
        // After save completes
    },
    // Field-specific triggers:
    field_name(frm) {
        // When field_name value changes
    }
});

// Child table events:
frappe.ui.form.on('Child DocType Name', {
    field_name(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        // Handle child row field change
    },
    child_table_add(frm, cdt, cdn) {
        // Row added
    },
    child_table_remove(frm, cdt, cdn) {
        // Row removed
    }
});
```

### hooks.py Structure

```python
app_name = "app_name"
app_title = "App Title"
app_publisher = "Publisher"
app_description = "Description"
app_email = "email@example.com"
app_license = "MIT"

# Doc Events
doc_events = {
    "DocType Name": {
        "validate": "app_name.module.events.validate_handler",
        "on_submit": "app_name.module.events.submit_handler",
    }
}

# Scheduler
scheduler_events = {
    "daily": ["app_name.tasks.daily_task"],
    "cron": {
        "0 */6 * * *": ["app_name.tasks.six_hourly"]
    }
}

# Permissions
permission_query_conditions = {
    "DocType": "app_name.permissions.get_conditions"
}

# Override
override_whitelisted_methods = {}
override_doctype_class = {}

# Fixtures
fixtures = []

# Includes
app_include_css = "/assets/app_name/css/app.css"
app_include_js = "/assets/app_name/js/app.js"
```

### App File Structure (What You Generate)

```
apps/<app_name>/
├── pyproject.toml
├── README.md
├── license.txt
├── requirements.txt
├── <app_name>/
│   ├── __init__.py
│   ├── hooks.py
│   ├── modules.txt
│   ├── patches.txt
│   ├── config/
│   │   ├── __init__.py
│   │   └── desktop.py
│   ├── <module_name>/
│   │   ├── __init__.py
│   │   └── doctype/
│   │       ├── __init__.py
│   │       └── <doctype_name>/
│   │           ├── __init__.py
│   │           ├── <doctype_name>.json
│   │           ├── <doctype_name>.py
│   │           ├── <doctype_name>.js
│   │           └── test_<doctype_name>.py
│   ├── public/
│   │   ├── css/
│   │   └── js/
│   ├── templates/
│   │   └── includes/
│   └── www/
```

### Naming Conventions
- **App name:** snake_case (e.g., `fleet_management`)
- **Module name:** Title Case in modules.txt, snake_case directory (e.g., `Fleet Management` / `fleet_management/`)
- **DocType name:** Title Case with spaces (e.g., `Vehicle Maintenance Log`)
- **DocType directory:** snake_case (e.g., `vehicle_maintenance_log/`)
- **Field names:** snake_case (e.g., `vehicle_registration_number`)
- **Python class:** PascalCase no spaces (e.g., `VehicleMaintenanceLog`)

### Workspace JSON

Every module should have a workspace for sidebar navigation:

```json
{
  "name": "Module Name",
  "module": "Module Name",
  "label": "Module Name",
  "category": "",
  "is_standard": 1,
  "content": [
    {
      "type": "header",
      "data": {"text": "Module Name", "level": 4}
    },
    {
      "type": "shortcut",
      "data": {
        "doctype": "DocType Name",
        "label": "DocType Name",
        "type": "DocType"
      }
    }
  ]
}
```

### Common Design Patterns

**1. Master-Transaction Pattern** (most common)
- Masters: Customer, Supplier, Item, Employee (reference data)
- Transactions: Sales Order, Purchase Order, Invoice (operational data that references masters)
- Transactions typically are submittable; Masters are not.

**2. Workflow Pattern**
- Use `is_submittable: 1` for approval flows
- Status field with Select type: Draft → Submitted → Cancelled
- Controller: on_submit() for approval logic, on_cancel() for reversal

**3. Child Table Pattern**
- Parent DocType has a `Table` field pointing to child DocType
- Child DocType has `istable: 1`
- Child has `parent`, `parenttype`, `parentfield` auto-fields
- Always include: `idx` (auto row number)

**4. Linked Documents Pattern**
- Use `Link` field to reference another DocType
- Use `fetch_from` to auto-populate fields from linked doc
- Use `Dynamic Link` when the target DocType varies

**5. Naming Series Pattern**
- For business docs: `naming_series:` autoname with Select field
- Options: `PREFIX-.YYYY.-.####` (e.g., `SO-2026-0001`)

### Bench Commands Reference

```bash
# App management
bench new-app <app_name>
bench --site <site> install-app <app_name>
bench --site <site> uninstall-app <app_name>
bench remove-app <app_name>

# Development
bench --site <site> migrate
bench build
bench clear-cache
bench --site <site> console
bench --site <site> mariadb

# Testing
bench --site <site> run-tests --app <app_name>
bench --site <site> run-tests --doctype "DocType Name"

# Site management
bench new-site <site_name> --admin-password <pw> --mariadb-root-password <pw>
bench use <site_name>
bench --site <site> set-admin-password <pw>

# Production
bench setup production <user>
bench restart
```

### Anti-Patterns to Avoid
1. NEVER use `autoname = "hash"` for business documents — humans need readable names
2. NEVER make every DocType submittable — only use for docs that need approval/amendment flow
3. NEVER skip permissions — every DocType needs at least one role with CRUD access
4. NEVER put business logic in client scripts only — always validate server-side
5. NEVER create DocTypes without `__init__.py` in every directory
6. NEVER forget to add modules to `modules.txt`
7. NEVER use spaces in fieldnames — always snake_case
8. NEVER use reserved words as fieldnames: `name`, `owner`, `creation`, `modified`, `modified_by`, `docstatus`, `idx`, `parent`, `parenttype`, `parentfield`
```

**Step 2: Verify the file is well-formed**

```bash
wc -l /home/harshwardhan/agentstack/shared/forge/CLAUDE.md
```

Expected: ~250-300 lines

**Step 3: Commit**

```bash
cd /home/harshwardhan/agentstack
git add shared/forge/
git commit -m "feat: add Frappe Forge agent directory and knowledge base"
```

---

### Task 3: Create DocType template files

**Files:**
- Create: `/home/harshwardhan/agentstack/shared/forge/templates/doctype.json.tmpl`
- Create: `/home/harshwardhan/agentstack/shared/forge/templates/controller.py.tmpl`
- Create: `/home/harshwardhan/agentstack/shared/forge/templates/client_script.js.tmpl`
- Create: `/home/harshwardhan/agentstack/shared/forge/templates/test.py.tmpl`
- Create: `/home/harshwardhan/agentstack/shared/forge/templates/hooks.py.tmpl`
- Create: `/home/harshwardhan/agentstack/shared/forge/templates/pyproject.toml.tmpl`

**Step 1: Create the DocType JSON template**

```json
{
  "name": "{{doctype_name}}",
  "module": "{{module_name}}",
  "autoname": "{{autoname}}",
  "naming_rule": "{{naming_rule}}",
  "track_changes": 1,
  "is_submittable": {{is_submittable}},
  "istable": {{istable}},
  "quick_entry": {{quick_entry}},
  "sort_field": "{{sort_field}}",
  "sort_order": "{{sort_order}}",
  "title_field": "{{title_field}}",
  "search_fields": "{{search_fields}}",
  "fields": [
    {{fields}}
  ],
  "permissions": [
    {{permissions}}
  ],
  "actions": [],
  "links": [],
  "engine": "InnoDB",
  "creation": "{{creation}}",
  "modified": "{{modified}}",
  "modified_by": "Administrator",
  "owner": "Administrator",
  "docstatus": 0,
  "doctype": "DocType"
}
```

**Step 2: Create the controller template**

```python
# Copyright (c) {{year}}, {{publisher}} and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class {{class_name}}(Document):
    def validate(self):
        {{validate_logic}}

    def before_save(self):
        pass

    def on_update(self):
        pass
```

**Step 3: Create the client script template**

```javascript
// Copyright (c) {{year}}, {{publisher}} and contributors
// For license information, please see license.txt

frappe.ui.form.on('{{doctype_name}}', {
    refresh(frm) {
        {{refresh_logic}}
    },
    validate(frm) {
        {{validate_logic}}
    }
});
```

**Step 4: Create the test template**

```python
# Copyright (c) {{year}}, {{publisher}} and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class Test{{class_name}}(FrappeTestCase):
    def test_create(self):
        doc = frappe.get_doc({
            "doctype": "{{doctype_name}}",
            {{test_fields}}
        })
        doc.insert()
        self.assertTrue(doc.name)

    def test_mandatory_fields(self):
        doc = frappe.get_doc({"doctype": "{{doctype_name}}"})
        self.assertRaises(frappe.MandatoryError, doc.insert)
```

**Step 5: Create hooks.py template**

```python
app_name = "{{app_name}}"
app_title = "{{app_title}}"
app_publisher = "{{publisher}}"
app_description = "{{description}}"
app_email = "{{email}}"
app_license = "MIT"

# Apps
# required_apps = []

# Doc Events
doc_events = {
    {{doc_events}}
}

# Scheduled Tasks
scheduler_events = {
    {{scheduler_events}}
}

# Fixtures
fixtures = [{{fixtures}}]
```

**Step 6: Create pyproject.toml template**

```toml
[project]
name = "{{app_name}}"
dynamic = ["version"]
requires-python = ">=3.10"
description = "{{description}}"

[build-system]
requires = ["flit_core >=3.4"]
build-backend = "flit_core.buildapi"

[tool.bench.frappe-dependencies]
frappe = ">=15.0.0"
```

**Step 7: Commit**

```bash
cd /home/harshwardhan/agentstack
git add shared/forge/templates/
git commit -m "feat: add Frappe Forge code generation templates"
```

---

### Task 4: Register Forge agent in agents.json

**Files:**
- Modify: `/home/harshwardhan/agentstack/agents.json`

**Step 1: Add the forge agent entry**

Add to the `agents` object in `agents.json`:

```json
"forge": {
  "description": "Frappe app builder. Generates complete Frappe apps from business descriptions.",
  "prompt": "You are Frappe Forge, an AI agent that generates complete, deployable Frappe Framework applications from natural language business descriptions. You work inside HNG's AgentStack.\n\nYour pipeline:\n1. UNDERSTAND - Ask clarifying questions about the business domain\n2. ARCHITECT - Design the data model (DocTypes, relationships, permissions)\n3. GENERATE - Write all app files (JSON, Python, JavaScript)\n4. INSTALL - Run bench commands to install and test\n5. ITERATE - Modify existing apps when requirements change\n\nHybrid autonomy:\n- Simple (≤5 DocTypes): Full auto\n- Medium (6-15 DocTypes): Checkpoint at data model\n- Complex (16+): Checkpoint at each phase\n\nReference your CLAUDE.md for complete Frappe schema reference, field types, hooks spec, and best practices.\n\nGenerated apps go to the Frappe bench at ~/frappe-bench/apps/\nReference templates at /home/harshwardhan/agentstack/shared/forge/templates/\nResearch docs at /home/harshwardhan/agentstack/shared/research/",
  "model": "opus",
  "cwd": "/home/harshwardhan/agentstack/shared/forge",
  "mcp_config": "/home/harshwardhan/agentstack/mcp-configs/forge.json",
  "flags": "--dangerously-skip-permissions"
}
```

**Step 2: Create the MCP config**

Create `/home/harshwardhan/agentstack/mcp-configs/forge.json`:

```json
{
  "mcpServers": {
    "fetch": {
      "command": "uvx",
      "args": ["mcp-server-fetch"],
      "env": {}
    },
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/home/harshwardhan/agentstack/shared/forge",
        "/home/harshwardhan/agentstack/shared/research"
      ]
    }
  }
}
```

**Step 3: Verify agents.json is valid JSON**

```bash
python3 -c "import json; json.load(open('/home/harshwardhan/agentstack/agents.json'))" && echo "Valid JSON"
```

Expected: `Valid JSON`

**Step 4: Commit**

```bash
cd /home/harshwardhan/agentstack
git add agents.json mcp-configs/forge.json
git commit -m "feat: register Frappe Forge agent in AgentStack"
```

---

### Task 5: Handle the --dangerously-skip-permissions flag in bot.py

**Files:**
- Modify: `/home/harshwardhan/agentstack/bot.py`

**Step 1: Find where agent commands are constructed**

Search bot.py for where tmux sessions are created for agents. Look for the section that constructs the `claude` command.

**Step 2: Add flags support**

When building the claude command for an agent, check if the agent config has a `flags` key. If so, append those flags to the command.

The exact code change depends on how bot.py currently constructs the claude command. Look for patterns like:
- `subprocess.run(["tmux", "new-session", ...])`
- `claude --model opus --prompt ...`
- Any agent launch logic

If agent launch is done through the terminal webapp (not bot.py directly), then the `flags` field in agents.json serves as documentation and the user adds `--dangerously-skip-permissions` when launching claude manually.

**Step 3: Test**

```bash
python3 -c "
import json
agents = json.load(open('/home/harshwardhan/agentstack/agents.json'))
forge = agents['agents']['forge']
print('Forge agent config:')
for k, v in forge.items():
    print(f'  {k}: {v[:80] if isinstance(v, str) and len(v) > 80 else v}')
"
```

**Step 4: Commit**

```bash
cd /home/harshwardhan/agentstack
git add bot.py
git commit -m "feat: support agent flags (dangerously-skip-permissions) in agent config"
```

---

### Task 6: Create the workspace CLAUDE.md for Forge

**Files:**
- Create: `/home/harshwardhan/agentstack/shared/forge/.claude/CLAUDE.md` (symlink or copy of the main CLAUDE.md)

Claude Code reads CLAUDE.md from the working directory. Since Forge's cwd is `/home/harshwardhan/agentstack/shared/forge/`, we need the knowledge base there.

**Step 1: Create .claude directory and symlink**

```bash
mkdir -p /home/harshwardhan/agentstack/shared/forge/.claude
# The CLAUDE.md we created in Task 2 is already at the right level
# Claude Code looks for CLAUDE.md in cwd, not .claude/CLAUDE.md
# So the file at /home/harshwardhan/agentstack/shared/forge/CLAUDE.md is correct
ls /home/harshwardhan/agentstack/shared/forge/CLAUDE.md
```

**Step 2: Verify Claude Code will find it**

```bash
# Claude Code searches: ./CLAUDE.md, ./.claude/CLAUDE.md, and parent directories
# Our CLAUDE.md at shared/forge/CLAUDE.md will be found when cwd is shared/forge/
echo "CLAUDE.md is at the correct location for cwd=/home/harshwardhan/agentstack/shared/forge/"
```

---

### Task 7: Dry run — generate a test app manually

**Files:**
- Create: `/home/harshwardhan/agentstack/shared/forge/generated-apps/test_task_app/` (complete app)

This task validates that the knowledge base and templates produce valid Frappe apps. We generate a simple "Task Management" app by hand (as Forge would) and verify the file structure is correct.

**Step 1: Create the app structure**

```bash
APP_DIR="/home/harshwardhan/agentstack/shared/forge/generated-apps/test_task_app"
mkdir -p "$APP_DIR/test_task_app/task_management/doctype/task_item"
mkdir -p "$APP_DIR/test_task_app/config"
mkdir -p "$APP_DIR/test_task_app/public/css"
mkdir -p "$APP_DIR/test_task_app/public/js"
mkdir -p "$APP_DIR/test_task_app/templates/includes"
mkdir -p "$APP_DIR/test_task_app/www"
```

**Step 2: Write the DocType JSON**

Write a valid `task_item.json` for a "Task Item" DocType with fields: title (Data, reqd), description (Text), status (Select: Open/In Progress/Completed), priority (Select: Low/Medium/High), assigned_to (Link: User), due_date (Date).

**Step 3: Write the controller, client script, test, hooks.py, pyproject.toml, modules.txt, __init__.py files**

Each file follows the patterns documented in CLAUDE.md.

**Step 4: Validate the JSON**

```bash
python3 -c "
import json
with open('$APP_DIR/test_task_app/task_management/doctype/task_item/task_item.json') as f:
    dt = json.load(f)
    print(f'DocType: {dt[\"name\"]}')
    print(f'Fields: {len(dt[\"fields\"])}')
    print(f'Permissions: {len(dt[\"permissions\"])}')
    print('Valid JSON ✓')
"
```

**Step 5: Verify complete file tree**

```bash
find $APP_DIR -type f | sort
```

Expected output should match the app structure documented in CLAUDE.md.

**Step 6: Commit**

```bash
cd /home/harshwardhan/agentstack
git add shared/forge/generated-apps/test_task_app/
git commit -m "feat: add test-generated Frappe app to validate Forge templates"
```

---

## Phase B: Infrastructure

### Task 8: Install Frappe Bench

**Step 1: Check prerequisites**

```bash
python3 --version  # Need 3.10+
node --version     # Need 18+
mysql --version    # Need MariaDB 10.6+
redis-cli --version
```

**Step 2: Install bench**

```bash
pip3 install frappe-bench
```

**Step 3: Initialize bench**

```bash
cd /home/harshwardhan
bench init frappe-bench --frappe-branch version-15
```

**Step 4: Create a development site**

```bash
cd /home/harshwardhan/frappe-bench
bench new-site dev.localhost --admin-password admin --mariadb-root-password <root_pw>
bench use dev.localhost
```

**Step 5: Verify**

```bash
cd /home/harshwardhan/frappe-bench
bench version
bench --site dev.localhost console <<< "print(frappe.utils.now())"
```

**Step 6: Commit (update CLAUDE.md with bench path)**

Update the Forge CLAUDE.md to include the actual bench path.

---

### Task 9: Connect Forge to Bench

**Files:**
- Modify: `/home/harshwardhan/agentstack/shared/forge/CLAUDE.md` (add bench path)
- Modify: `/home/harshwardhan/agentstack/agents.json` (update forge cwd or add bench path to prompt)
- Modify: `/home/harshwardhan/agentstack/mcp-configs/forge.json` (add bench apps dir to filesystem access)

**Step 1: Update MCP config to include bench directory**

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/home/harshwardhan/agentstack/shared/forge",
        "/home/harshwardhan/agentstack/shared/research",
        "/home/harshwardhan/frappe-bench/apps"
      ]
    }
  }
}
```

**Step 2: Verify Forge can write to bench apps directory**

```bash
touch /home/harshwardhan/frappe-bench/apps/.forge-test && rm /home/harshwardhan/frappe-bench/apps/.forge-test
echo "Write access confirmed"
```

**Step 3: Commit**

```bash
cd /home/harshwardhan/agentstack
git add shared/forge/CLAUDE.md agents.json mcp-configs/forge.json
git commit -m "feat: connect Forge agent to Frappe bench"
```

---

### Task 10: Test end-to-end — install the test app on bench

**Step 1: Copy test app to bench**

```bash
cp -r /home/harshwardhan/agentstack/shared/forge/generated-apps/test_task_app /home/harshwardhan/frappe-bench/apps/test_task_app
```

**Step 2: Install on site**

```bash
cd /home/harshwardhan/frappe-bench
bench --site dev.localhost install-app test_task_app
bench --site dev.localhost migrate
```

**Step 3: Verify DocType exists**

```bash
cd /home/harshwardhan/frappe-bench
bench --site dev.localhost console <<< "
doc = frappe.new_doc('Task Item')
doc.title = 'Test Task'
doc.status = 'Open'
doc.priority = 'Medium'
doc.insert()
print(f'Created: {doc.name}')
frappe.db.commit()
"
```

**Step 4: Run tests**

```bash
cd /home/harshwardhan/frappe-bench
bench --site dev.localhost run-tests --app test_task_app
```

Expected: Tests pass.

**Step 5: Clean up test app**

```bash
cd /home/harshwardhan/frappe-bench
bench --site dev.localhost uninstall-app test_task_app --yes
bench remove-app test_task_app --no-backup
```

---

## Phase C: First Client

### Task 11: Use Forge to build the client CRM

This is the real test. Open the Forge agent (via Telegram or directly) and give it the client's business requirements. Forge should:

1. Ask clarifying questions about the CRM needs
2. Design the data model
3. Generate the complete app
4. Install it on bench
5. Run tests

**Step 1: Launch Forge**

Via Telegram: Select the `forge` agent
Or directly:

```bash
cd /home/harshwardhan/agentstack/shared/forge
claude --model opus --dangerously-skip-permissions
```

**Step 2: Give it the client brief**

Describe the client's CRM needs. Forge handles the rest.

**Step 3: Review and iterate**

Review the generated app. Ask Forge to modify as needed.

---

## Summary

| Phase | Tasks | What's Built |
|-------|-------|-------------|
| **A: Engine** | Tasks 1-7 | Forge agent with knowledge base, templates, registered in AgentStack |
| **B: Infrastructure** | Tasks 8-10 | Frappe bench running, connected to Forge, end-to-end validated |
| **C: Client** | Task 11 | First real CRM app generated and deployed |

Total estimated time:
- Phase A: 1-2 hours (mostly file creation and configuration)
- Phase B: 1-2 hours (bench installation, depends on system state)
- Phase C: 2-4 hours (depends on client requirements complexity)
