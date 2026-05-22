#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { FoundationStack } from '../lib/foundation-stack';
import { LambdaStack } from '../lib/lambda-stack';
import { GuardrailsStack } from '../lib/guardrails-stack';
import { AgentsStack } from '../lib/agents-stack';
import { WorkflowStack } from '../lib/workflow-stack';
import { ObservabilityStack } from '../lib/observability-stack';

/**
 * Aegis-Tactical CDK Application
 *
 * Deploys the full multi-agent intelligence system in dependency order:
 *   1. FoundationStack  — S3, OpenSearch Serverless, Bedrock Knowledge Base
 *   2. LambdaStack      — Lambda tool functions
 *   3. GuardrailsStack  — Bedrock Guardrails
 *   4. AgentsStack      — All 4 Bedrock Agents
 *   5. WorkflowStack    — Step Functions mission executor
 *   6. ObservabilityStack — CloudWatch dashboards & alarms
 */
const app = new cdk.App();

const env: cdk.Environment = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: app.node.tryGetContext('aegis:region') || process.env.CDK_DEFAULT_REGION || 'us-east-1',
};

const tags = {
  Project: 'AegisTactical',
  ManagedBy: 'CDK',
  Environment: app.node.tryGetContext('aegis:environment') || 'dev',
};

// ────────────────────────────────────────────────────────────────────────────
// Phase 1: Foundation — Data Layer
// ────────────────────────────────────────────────────────────────────────────
const foundationStack = new FoundationStack(app, 'AegisFoundationStack', {
  env,
  tags,
  description: 'Aegis-Tactical: S3 ground truth bucket, OpenSearch Serverless, Bedrock Knowledge Base',
});

// ────────────────────────────────────────────────────────────────────────────
// Phase 1b: Lambda Tools
// ────────────────────────────────────────────────────────────────────────────
const lambdaStack = new LambdaStack(app, 'AegisLambdaStack', {
  env,
  tags,
  description: 'Aegis-Tactical: Lambda tool functions (fetch_news, fetch_rss, fetch_github, write_report)',
  groundTruthBucket: foundationStack.groundTruthBucket,
});
lambdaStack.addDependency(foundationStack);

// ────────────────────────────────────────────────────────────────────────────
// Phase 3: Guardrails (deployed before Agents so we can reference the ID)
// ────────────────────────────────────────────────────────────────────────────
const guardrailsStack = new GuardrailsStack(app, 'AegisGuardrailsStack', {
  env,
  tags,
  description: 'Aegis-Tactical: Bedrock Guardrails for content safety and PII protection',
});

// ────────────────────────────────────────────────────────────────────────────
// Phase 2: Agents
// ────────────────────────────────────────────────────────────────────────────
const agentsStack = new AgentsStack(app, 'AegisAgentsStack', {
  env,
  tags,
  description: 'Aegis-Tactical: Bedrock Agents (Supervisor, Scout, Analyst, Sentinel)',
  knowledgeBaseId: foundationStack.knowledgeBaseId,
  knowledgeBaseArn: foundationStack.knowledgeBaseArn,
  functionArns: lambdaStack.functionArns,
  fetchNewsFunction: lambdaStack.fetchNewsFunction,
  fetchRssFunction: lambdaStack.fetchRssFunction,
  fetchGithubFunction: lambdaStack.fetchGithubFunction,
  writeReportFunction: lambdaStack.writeReportFunction,
  guardrailId: guardrailsStack.guardrailId,
  guardrailVersion: guardrailsStack.guardrailVersion,
});
agentsStack.addDependency(foundationStack);
agentsStack.addDependency(lambdaStack);
agentsStack.addDependency(guardrailsStack);

// ────────────────────────────────────────────────────────────────────────────
// Phase 4: Workflow
// ────────────────────────────────────────────────────────────────────────────
const workflowStack = new WorkflowStack(app, 'AegisWorkflowStack', {
  env,
  tags,
  description: 'Aegis-Tactical: Step Functions mission executor with retry and escalation logic',
  supervisorAgentId: agentsStack.supervisorAgentId,
  supervisorAgentArn: agentsStack.supervisorAgentArn,
  fetchNewsFunction: lambdaStack.fetchNewsFunction,
  fetchRssFunction: lambdaStack.fetchRssFunction,
  fetchGithubFunction: lambdaStack.fetchGithubFunction,
  writeReportFunction: lambdaStack.writeReportFunction,
});
workflowStack.addDependency(agentsStack);
workflowStack.addDependency(lambdaStack);

// ────────────────────────────────────────────────────────────────────────────
// Phase 4: Observability
// ────────────────────────────────────────────────────────────────────────────
const observabilityStack = new ObservabilityStack(app, 'AegisObservabilityStack', {
  env,
  tags,
  description: 'Aegis-Tactical: CloudWatch dashboards, alarms, and SNS alerts',
  stateMachine: workflowStack.stateMachine,
  fetchNewsFunction: lambdaStack.fetchNewsFunction,
  fetchRssFunction: lambdaStack.fetchRssFunction,
  fetchGithubFunction: lambdaStack.fetchGithubFunction,
  writeReportFunction: lambdaStack.writeReportFunction,
});
observabilityStack.addDependency(workflowStack);
observabilityStack.addDependency(lambdaStack);

app.synth();
