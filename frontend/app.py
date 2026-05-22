import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError
import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(
    page_title="Aegis Mission Console",
    layout="wide",
    initial_sidebar_state="expanded",
)


CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Serif:ital,wght@0,500;1,400&display=swap');

:root {
  --bg: #f2ecdd;
  --paper: #fffaf0;
  --ink: #14232d;
  --muted: #42525d;
  --line: #cebda3;
  --accent: #006f7a;
  --warning: #c87400;
  --ok: #007a3f;
  --danger: #b53032;
}

html, body, [class*="css"], p, span, label, li {
  font-family: 'Space Grotesk', sans-serif;
  color: var(--ink) !important;
}

.stApp {
  background:
    radial-gradient(circle at 8% 5%, #f9f4e8 0%, #f2ecdd 48%, #ece3d2 100%),
    repeating-linear-gradient(
      45deg,
      rgba(20, 35, 45, 0.02) 0,
      rgba(20, 35, 45, 0.02) 1px,
      transparent 1px,
      transparent 12px
    );
}

.block-container {
  padding-top: 1.6rem;
  max-width: 1200px;
}

.hero {
  border: 1px solid var(--line);
  background: linear-gradient(140deg, #fffdf8 0%, #f8f2e7 62%, #efe5d3 100%);
  box-shadow: 0 10px 26px rgba(20, 35, 45, 0.06);
  padding: 1.1rem 1.3rem;
  border-radius: 14px;
  margin-bottom: 1.1rem;
}

.hero h1 {
  font-family: 'IBM Plex Serif', serif;
  margin: 0;
  font-size: 2.05rem;
  color: #101c25 !important;
}

.hero p {
  margin-top: 0.5rem;
  margin-bottom: 0;
  color: #30414d !important;
}

.chip-row {
  margin-top: 0.85rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.chip {
  font-size: 0.73rem;
  padding: 0.24rem 0.56rem;
  border-radius: 999px;
  border: 1px solid #bfcfbe;
  background: #edf4ea;
  color: #2a3d2c !important;
}

.metric-card {
  border: 1px solid var(--line);
  border-left: 6px solid var(--accent);
  border-radius: 12px;
  background: var(--paper);
  min-height: 98px;
  padding: 0.95rem 1rem;
  box-shadow: 0 8px 18px rgba(20, 35, 45, 0.04);
}

.metric-label {
  font-size: 0.76rem;
  color: #4d5d68 !important;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.metric-value {
  margin-top: 0.3rem;
  font-size: 1.03rem;
  font-weight: 700;
  color: #12212b !important;
}

a {
  color: var(--accent) !important;
  font-weight: 600;
}

.stButton > button {
  border-radius: 10px;
  border: 1px solid var(--accent);
  color: var(--ink) !important;
  background: #e7f6f7;
  font-weight: 600;
}

.stButton > button:hover {
  border-color: var(--warning);
  color: #2d1a00;
  background: #fff4de;
}

.stButton > button:disabled {
  border-color: #9bb0bb !important;
  color: #4f616d !important;
  background: #dce4e8 !important;
  opacity: 1 !important;
}

.stButton > button * {
  color: inherit !important;
}

.stDownloadButton > button {
  border-radius: 10px;
  border: 1px solid var(--accent) !important;
  color: var(--ink) !important;
  background: #e7f6f7 !important;
  font-weight: 600;
}

.stDownloadButton > button:hover:not(:disabled) {
  border-color: var(--warning) !important;
  color: #2d1a00 !important;
  background: #fff4de !important;
}

.stDownloadButton > button:disabled {
  border-color: #9bb0bb !important;
  color: #4f616d !important;
  background: #dce4e8 !important;
  opacity: 1 !important;
}

.stDownloadButton > button * {
  color: inherit !important;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.77rem;
  border-radius: 999px;
  padding: 0.22rem 0.58rem;
  border: 1px solid transparent;
}

.status-ok {
  background: #e8f7ee;
  border-color: #a8ddbb;
  color: #0e5e33 !important;
}

.status-running {
  background: #eaf4fd;
  border-color: #a3cae9;
  color: #0b4f7d !important;
}

.status-failed {
  background: #ffeceb;
  border-color: #f2b0ae;
  color: #8e1f22 !important;
}

.status-other {
  background: #f1f3f5;
  border-color: #ced5db;
  color: #30404d !important;
}

section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #172634 0%, #1d3042 100%);
  border-right: 1px solid #34485b;
}

section[data-testid="stSidebar"] * {
  color: #eef6ff !important;
}

section[data-testid="stSidebar"] .stButton > button {
  background: #20445f;
  border-color: #5f95bc;
  color: #f0f7ff !important;
}

section[data-testid="stSidebar"] .stButton > button:hover {
  background: #2e5e81;
}

section[data-testid="stSidebar"] .stButton > button:disabled {
  background: #3a5367 !important;
  border-color: #6e8ca4 !important;
  color: #d9e7f5 !important;
  opacity: 1 !important;
}

section[data-testid="stSidebar"] .stDownloadButton > button {
  background: #20445f !important;
  border-color: #5f95bc !important;
  color: #f0f7ff !important;
}

section[data-testid="stSidebar"] .stDownloadButton > button:hover:not(:disabled) {
  background: #2e5e81 !important;
}

section[data-testid="stSidebar"] .stDownloadButton > button:disabled {
  background: #3a5367 !important;
  border-color: #6e8ca4 !important;
  color: #d9e7f5 !important;
  opacity: 1 !important;
}

div[data-testid="stTabs"] button {
  color: #3d4f5b !important;
  font-weight: 600;
}

div[data-testid="stTabs"] button[aria-selected="true"] {
  color: #11212b !important;
}

div[data-testid="stAlert"] {
  border-radius: 10px;
}
</style>
"""


def utcnow_name() -> str:
  return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def parse_s3_uri(uri: str) -> Tuple[str, str]:
  if not uri.startswith("s3://"):
    raise ValueError("Expected s3:// URI")
  path = uri[5:]
  bucket, _, key = path.partition("/")
  if not bucket or not key:
    raise ValueError("Invalid s3:// URI")
  return bucket, key


def json_or_text(value: str) -> Any:
  try:
    return json.loads(value)
  except Exception:
    return value


def pretty_datetime(value: Any) -> str:
  if not value:
    return "-"

  if isinstance(value, datetime):
    try:
      return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
      return str(value)

  return str(value)


def first_present(data: Dict[str, Any], keys: List[str]) -> Optional[Any]:
  for key in keys:
    value = data.get(key)
    if value is None:
      continue
    if isinstance(value, str) and not value.strip():
      continue
    return value
  return None


def human_label(value: Any) -> str:
  if value is None:
    return "-"
  text = str(value).strip()
  if not text:
    return "-"
  return text.replace("_", " ").title()


def format_confidence(value: Any) -> str:
  if value is None:
    return "-"

  try:
    score = float(value)
  except Exception:
    return str(value)

  if score < 0:
    return "-"
  if score <= 1:
    return f"{score:.2f} ({score * 100:.0f}%)"
  if score <= 100:
    return f"{score:.1f}%"
  return f"{score:.2f}"


def status_label(status: str) -> str:
  labels = {
    "RUNNING": "In Progress",
    "SUCCEEDED": "Completed",
    "FAILED": "Failed",
    "ABORTED": "Stopped",
    "TIMED_OUT": "Timed Out",
  }
  return labels.get(status, status.title().replace("_", " "))


def status_class(status: str) -> str:
  if status == "SUCCEEDED":
    return "status-ok"
  if status == "RUNNING":
    return "status-running"
  if status in {"FAILED", "TIMED_OUT", "ABORTED"}:
    return "status-failed"
  return "status-other"


def status_icon(status: str) -> str:
  icons = {
    "RUNNING": "o",
    "SUCCEEDED": "+",
    "FAILED": "x",
    "ABORTED": "-",
    "TIMED_OUT": "!",
  }
  return icons.get(status, "o")


def status_badge(status: str) -> str:
  return (
    f'<span class="status-badge {status_class(status)}">'
    f"<span>{status_icon(status)}</span><span>{status_label(status)}</span>"
    "</span>"
  )


def summarize_executions(rows: List[Dict[str, Any]]) -> Dict[str, int]:
  summary = {
    "RUNNING": 0,
    "SUCCEEDED": 0,
    "FAILED": 0,
    "ABORTED": 0,
    "TIMED_OUT": 0,
  }

  for row in rows:
    status = str(row.get("status", ""))
    if status in summary:
      summary[status] += 1

  return summary


def friendly_execution_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
  friendly: List[Dict[str, str]] = []
  for row in rows:
    status = str(row.get("status", "UNKNOWN"))
    execution_arn = str(row.get("executionArn", ""))
    run_id = execution_arn.split(":")[-1] if execution_arn else "-"
    friendly.append(
      {
        "Mission Run": run_id,
        "Status": status_label(status),
        "Started": pretty_datetime(row.get("started")),
        "Finished": pretty_datetime(row.get("stopped")),
        "Execution ARN": execution_arn,
      }
    )
  return friendly


def pretty_size(num_bytes: Any) -> str:
  try:
    value = float(num_bytes)
  except Exception:
    return "-"

  units = ["B", "KB", "MB", "GB"]
  index = 0
  while value >= 1024 and index < len(units) - 1:
    value /= 1024
    index += 1
  return f"{value:.1f} {units[index]}"


def friendly_report_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
  return [
    {
      "Report File": str(item.get("key", "")),
      "Updated": pretty_datetime(item.get("lastModified")),
      "Size": pretty_size(item.get("size", 0)),
    }
    for item in rows
  ]


def alarm_state_label(state: str) -> str:
  labels = {
    "OK": "Healthy",
    "ALARM": "Needs Attention",
    "INSUFFICIENT_DATA": "No Recent Data",
  }
  return labels.get(state, state.title().replace("_", " "))


def summarize_alarms(rows: List[Dict[str, Any]]) -> Dict[str, int]:
  summary = {"OK": 0, "ALARM": 0, "INSUFFICIENT_DATA": 0}
  for row in rows:
    state = str(row.get("state", ""))
    if state in summary:
      summary[state] += 1
  return summary


@st.cache_resource(show_spinner=False)
def make_clients(region: str) -> Dict[str, Any]:
  session = boto3.Session(region_name=region)
  return {
    "cloudformation": session.client("cloudformation"),
    "stepfunctions": session.client("stepfunctions"),
    "s3": session.client("s3"),
    "cloudwatch": session.client("cloudwatch"),
  }


@st.cache_data(show_spinner=False, ttl=20)
def stack_outputs(region: str, stack_name: str) -> Dict[str, str]:
  cfn = make_clients(region)["cloudformation"]
  response = cfn.describe_stacks(StackName=stack_name)
  outputs = response["Stacks"][0].get("Outputs", [])
  return {item["OutputKey"]: item["OutputValue"] for item in outputs}


@st.cache_data(show_spinner=False, ttl=15)
def load_runtime_config(region: str) -> Dict[str, Optional[str]]:
  workflow = stack_outputs(region, "AegisWorkflowStack")
  foundation = stack_outputs(region, "AegisFoundationStack")
  observability = stack_outputs(region, "AegisObservabilityStack")

  return {
    "state_machine_arn": workflow.get("StateMachineArn"),
    "state_machine_name": workflow.get("StateMachineName"),
    "reports_bucket": foundation.get("GroundTruthBucketName"),
    "dashboard_url": observability.get("DashboardUrl"),
  }


def start_mission(region: str, state_machine_arn: str, objective: str) -> str:
  sfn = make_clients(region)["stepfunctions"]
  run_name = f"ui-{utcnow_name()}"
  payload = {"objective": objective}
  response = sfn.start_execution(
    stateMachineArn=state_machine_arn,
    name=run_name,
    input=json.dumps(payload),
  )
  return response["executionArn"]


@st.cache_data(show_spinner=False, ttl=10)
def recent_executions(region: str, state_machine_arn: str, max_results: int = 15) -> List[Dict[str, Any]]:
  sfn = make_clients(region)["stepfunctions"]
  response = sfn.list_executions(stateMachineArn=state_machine_arn, maxResults=max_results)
  rows: List[Dict[str, Any]] = []

  for item in response.get("executions", []):
    rows.append(
      {
        "name": item.get("name"),
        "status": item.get("status"),
        "started": item.get("startDate"),
        "stopped": item.get("stopDate"),
        "executionArn": item.get("executionArn"),
      }
    )
  return rows


def execution_details(region: str, execution_arn: str) -> Dict[str, Any]:
  sfn = make_clients(region)["stepfunctions"]
  response = sfn.describe_execution(executionArn=execution_arn)

  output_obj: Any = None
  if "output" in response:
    output_obj = json_or_text(response["output"])

  return {
    "status": response.get("status"),
    "startDate": response.get("startDate"),
    "stopDate": response.get("stopDate"),
    "input": json_or_text(response.get("input", "{}")),
    "output": output_obj,
  }


@st.cache_data(show_spinner=False, ttl=20)
def list_reports(region: str, bucket: str, prefix: str = "reports/") -> List[Dict[str, Any]]:
  s3 = make_clients(region)["s3"]
  response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=100)
  objects = response.get("Contents", [])

  rows = [
    {
      "key": item.get("Key"),
      "lastModified": item.get("LastModified"),
      "size": item.get("Size"),
    }
    for item in objects
    if item.get("Key", "").endswith(".md")
  ]

  rows.sort(key=lambda row: row["lastModified"], reverse=True)
  return rows


@st.cache_data(show_spinner=False, ttl=20)
def read_report_bytes(region: str, uri: str) -> bytes:
  s3 = make_clients(region)["s3"]
  bucket, key = parse_s3_uri(uri)
  response = s3.get_object(Bucket=bucket, Key=key)
  return response["Body"].read()


def read_report(region: str, uri: str) -> str:
  return read_report_bytes(region, uri).decode("utf-8", errors="replace")


@st.cache_data(show_spinner=False, ttl=20)
def alarm_overview(region: str) -> List[Dict[str, Any]]:
  cloudwatch = make_clients(region)["cloudwatch"]
  response = cloudwatch.describe_alarms(MaxRecords=100)
  rows: List[Dict[str, Any]] = []

  for alarm in response.get("MetricAlarms", []):
    name = alarm.get("AlarmName", "")
    if "aegis" in name.lower() or "mission" in name.lower() or "fetch_" in name.lower():
      rows.append(
        {
          "alarm": name,
          "state": alarm.get("StateValue"),
          "namespace": alarm.get("Namespace"),
          "metric": alarm.get("MetricName"),
        }
      )

  rows.sort(key=lambda row: row["alarm"])
  return rows


def render_top_cards(runtime: Dict[str, Optional[str]]) -> None:
  col1, col2, col3 = st.columns(3)
  machine_name = runtime.get("state_machine_name") or "Unknown"
  machine_name = machine_name.replace("-", " ").title()

  with col1:
    st.markdown(
      f"""
      <div class=\"metric-card\">
        <div class=\"metric-label\">Mission Engine</div>
        <div class=\"metric-value\">{machine_name}</div>
      </div>
      """,
      unsafe_allow_html=True,
    )

  with col2:
    st.markdown(
      f"""
      <div class=\"metric-card\" style=\"border-left-color:#c87400;\">
        <div class=\"metric-label\">Report Vault</div>
        <div class=\"metric-value\">{runtime.get('reports_bucket') or 'Unknown'}</div>
      </div>
      """,
      unsafe_allow_html=True,
    )

  with col3:
    dash = runtime.get("dashboard_url")
    dash_html = f"<a href=\"{dash}\" target=\"_blank\">Open Live Operations Board</a>" if dash else "Unavailable"
    st.markdown(
      f"""
      <div class=\"metric-card\" style=\"border-left-color:#2d7b47;\">
        <div class=\"metric-label\">Live Monitoring</div>
        <div class=\"metric-value\">{dash_html}</div>
      </div>
      """,
      unsafe_allow_html=True,
    )


def main() -> None:
  st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

  st.markdown(
    """
    <div class="hero">
      <h1>Aegis Mission Console</h1>
      <p>Mission control for non-technical operators: launch investigations, track progress, and read finished intelligence reports.</p>
      <div class="chip-row">
        <span class="chip">Launch Mission</span>
        <span class="chip">Track Runs</span>
        <span class="chip">Read Reports</span>
        <span class="chip">Monitor Health</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
  )

  default_region = st.session_state.get("region", "us-east-1")
  region = st.sidebar.text_input("AWS Region", value=default_region)
  st.session_state["region"] = region

  st.sidebar.markdown("---")
  st.sidebar.subheader("Live View")
  auto_refresh = st.sidebar.toggle(
    "Auto-refresh mission data",
    value=False,
    help="Refreshes mission and health data automatically.",
  )
  refresh_seconds = st.sidebar.slider("Refresh interval (seconds)", 10, 120, 20, step=5)

  if st.sidebar.button("Reload Live Data"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

  if auto_refresh:
    components.html(
      f"""
      <script>
        setTimeout(function() {{
          window.parent.location.reload();
        }}, {refresh_seconds * 1000});
      </script>
      """,
      height=0,
      width=0,
    )

  try:
    runtime = load_runtime_config(region)
  except (ClientError, BotoCoreError, KeyError) as exc:
    st.error("Failed to load stack metadata. Check AWS credentials, region, and deployed stacks.")
    st.exception(exc)
    return

  render_top_cards(runtime)

  state_machine_arn = runtime.get("state_machine_arn")
  reports_bucket = runtime.get("reports_bucket")

  tab_launch, tab_runs, tab_reports, tab_health = st.tabs(
    ["Launch Mission", "Mission Runs", "Reports", "System Health"]
  )

  with tab_launch:
    if not state_machine_arn:
      st.warning("State machine ARN not found. Deploy AegisWorkflowStack first.")
    else:
      objective = st.text_area(
        "What should Aegis investigate?",
        value="Investigate recent supply-chain intelligence signals related to our dependencies.",
        height=110,
      )

      if st.button("Launch Mission", type="primary"):
        if not objective.strip():
          st.warning("Mission objective cannot be empty.")
        else:
          try:
            execution_arn = start_mission(region, state_machine_arn, objective.strip())
            st.session_state["last_execution_arn"] = execution_arn
            st.success("Mission launched successfully.")
            st.write(f"Execution ARN: {execution_arn}")
          except (ClientError, BotoCoreError) as exc:
            st.error("Mission launch failed.")
            st.exception(exc)

      if st.session_state.get("last_execution_arn"):
        st.info("Latest mission launched in this browser session.")
        st.write(st.session_state["last_execution_arn"])

  with tab_runs:
    if not state_machine_arn:
      st.warning("State machine ARN not found.")
    else:
      try:
        executions = recent_executions(region, state_machine_arn)
      except (ClientError, BotoCoreError) as exc:
        st.error("Could not read execution history.")
        st.exception(exc)
        executions = []

      summary = summarize_executions(executions)
      m1, m2, m3, m4, m5 = st.columns(5)
      m1.metric("In Progress", summary["RUNNING"])
      m2.metric("Completed", summary["SUCCEEDED"])
      m3.metric("Failed", summary["FAILED"])
      m4.metric("Stopped", summary["ABORTED"])
      m5.metric("Timed Out", summary["TIMED_OUT"])

      if not executions:
        st.info("No executions found yet.")
      else:
        st.dataframe(
          friendly_execution_rows(executions),
          hide_index=True,
          use_container_width=True,
        )

        execution_labels = {
          str(row.get("executionArn", "")): (
            f"{row.get('name', 'Unknown run')} - {status_label(str(row.get('status', 'UNKNOWN')))}"
          )
          for row in executions
        }

        selected_arn = st.selectbox(
          "Select a mission run",
          options=[row["executionArn"] for row in executions],
          format_func=lambda arn: execution_labels.get(arn, arn.split(":")[-1]),
        )

        if selected_arn:
          try:
            details = execution_details(region, selected_arn)
          except (ClientError, BotoCoreError) as exc:
            st.error("Could not load execution details.")
            st.exception(exc)
            details = {}

          if details:
            status = str(details.get("status", "UNKNOWN"))
            st.markdown(status_badge(status), unsafe_allow_html=True)

            c1, c2, c3 = st.columns(3)
            c1.metric("Mission Run", selected_arn.split(":")[-1])
            c2.metric("Started", pretty_datetime(details.get("startDate", "-")))
            c3.metric("Finished", pretty_datetime(details.get("stopDate", "-")))

            input_data = details.get("input")
            if isinstance(input_data, dict) and input_data.get("objective"):
              st.caption("Mission objective")
              st.write(str(input_data.get("objective")))

            output = details.get("output")

            if isinstance(output, dict):
              direct_answer = first_present(output, ["directAnswer", "direct_answer"])
              analyst_verdict = first_present(output, ["analystVerdict", "analyst_verdict"])
              confidence_score = first_present(output, ["confidenceScore", "confidence_score"])
              evidence_quality = first_present(output, ["evidenceQuality", "evidence_quality"])
              sentinel_route = first_present(output, ["verdict", "sentinelVerdict", "suggested_sentinel_verdict"])

              if (
                direct_answer is not None
                or analyst_verdict is not None
                or confidence_score is not None
                or evidence_quality is not None
                or sentinel_route is not None
              ):
                st.subheader("Mission Assessment")
                a1, a2, a3 = st.columns(3)
                a1.metric("Analyst Verdict", human_label(analyst_verdict))
                a2.metric("Confidence", format_confidence(confidence_score))
                if evidence_quality is not None:
                  a3.metric("Evidence Quality", human_label(evidence_quality))
                else:
                  a3.metric("Sentinel Route", human_label(sentinel_route))

                if direct_answer is not None:
                  st.info(str(direct_answer))

            st.subheader("Execution Output")
            st.json(output if output is not None else {"output": None})

            report_uri = None
            if isinstance(output, dict):
              report_uri = first_present(output, ["reportLocation", "report_location"])

            if report_uri and str(report_uri).startswith("s3://"):
              run_id = selected_arn.split(":")[-1]
              st.caption("A report is available for this run.")

              report_bytes: Optional[bytes] = None
              try:
                report_bytes = read_report_bytes(region, str(report_uri))
              except Exception as exc:
                st.error("Failed to load report from S3.")
                st.exception(exc)

              if report_bytes is not None:
                action_col1, action_col2 = st.columns([1, 1])
                with action_col1:
                  show_preview = st.button("Preview Mission Report", key=f"preview-{run_id}")
                with action_col2:
                  st.download_button(
                    "Download Report",
                    data=report_bytes,
                    file_name=f"{run_id}.md",
                    mime="text/markdown",
                    key=f"download-{run_id}",
                  )

                if show_preview:
                  st.markdown(report_bytes.decode("utf-8", errors="replace"))

  with tab_reports:
    if not reports_bucket:
      st.warning("Reports bucket not found in stack outputs.")
    else:
      try:
        report_rows = list_reports(region, reports_bucket)
      except (ClientError, BotoCoreError) as exc:
        st.error("Could not list reports.")
        st.exception(exc)
        report_rows = []

      if not report_rows:
        st.info("No report files found yet.")
      else:
        st.dataframe(
          friendly_report_rows(report_rows),
          hide_index=True,
          use_container_width=True,
        )

        latest_key = str(report_rows[0].get("key", ""))
        latest_uri = f"s3://{reports_bucket}/{latest_key}"
        st.caption(f"Latest report: {latest_key}")

        latest_col1, latest_col2 = st.columns([1, 1])
        with latest_col1:
          show_latest = st.button("Preview Latest Report", key="preview-latest-report")
        with latest_col2:
          try:
            latest_bytes = read_report_bytes(region, latest_uri)
            st.download_button(
              "Download Latest Report",
              data=latest_bytes,
              file_name=latest_key.split("/")[-1] if latest_key else "latest-report.md",
              mime="text/markdown",
              key="download-latest-report",
            )
          except Exception as exc:
            st.error("Could not download latest report.")
            st.exception(exc)

        if show_latest:
          try:
            st.markdown(read_report(region, latest_uri))
          except Exception as exc:
            st.error("Could not open latest report.")
            st.exception(exc)

        selected_key = st.selectbox(
          "Select report file",
          options=[str(row["key"]) for row in report_rows],
          format_func=lambda key: key.split("/")[-1],
        )

        if selected_key:
          uri = f"s3://{reports_bucket}/{selected_key}"
          selected_col1, selected_col2 = st.columns([1, 1])
          with selected_col1:
            open_selected = st.button("Open Selected Report", key=f"open-{selected_key}")
          with selected_col2:
            try:
              selected_bytes = read_report_bytes(region, uri)
              st.download_button(
                "Download Selected",
                data=selected_bytes,
                file_name=selected_key.split("/")[-1],
                mime="text/markdown",
                key=f"download-{selected_key}",
              )
            except Exception as exc:
              st.error("Could not prepare selected report download.")
              st.exception(exc)

          if open_selected:
            try:
              st.markdown(read_report(region, uri))
            except Exception as exc:
              st.error("Could not read selected report.")
              st.exception(exc)

  with tab_health:
    try:
      alarms = alarm_overview(region)
    except (ClientError, BotoCoreError) as exc:
      st.error("Could not load CloudWatch alarms.")
      st.exception(exc)
      alarms = []

    if alarms:
      alarm_summary = summarize_alarms(alarms)
      a1, a2, a3 = st.columns(3)
      a1.metric("Healthy", alarm_summary["OK"])
      a2.metric("Needs Attention", alarm_summary["ALARM"])
      a3.metric("No Recent Data", alarm_summary["INSUFFICIENT_DATA"])

      friendly_alarms = [
        {
          "Alarm": str(row.get("alarm", "")),
          "State": alarm_state_label(str(row.get("state", ""))),
          "Metric": str(row.get("metric", "")),
          "Namespace": str(row.get("namespace", "")),
        }
        for row in alarms
      ]
      st.dataframe(friendly_alarms, hide_index=True, use_container_width=True)
    else:
      st.info("No Aegis alarms detected.")

    dashboard_url = runtime.get("dashboard_url")
    if dashboard_url:
      st.markdown(f"Open operations dashboard: [Aegis Tactical Dashboard]({dashboard_url})")


if __name__ == "__main__":
  main()
