import * as cdk from 'aws-cdk-lib';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { Construct } from 'constructs';

export interface AgentsStackProps extends cdk.StackProps {
  /** Knowledge Base ID for RAG */
  knowledgeBaseId: string;
  /** Knowledge Base ARN */
  knowledgeBaseArn: string;
  /** Lambda function ARNs keyed by name */
  functionArns: { [key: string]: string };
  /** Lambda functions for granting invoke permissions */
  fetchNewsFunction: lambda.IFunction;
  fetchRssFunction: lambda.IFunction;
  fetchGithubFunction: lambda.IFunction;
  writeReportFunction: lambda.IFunction;
  /** Guardrail ID for the Sentinel agent */
  guardrailId: string;
  /** Guardrail version */
  guardrailVersion: string;
}

/**
 * AgentsStack — Phase 2
 *
 * Provisions all four Bedrock Agents with action groups:
 *   - Scout Agent (Nova Lite) — news, RSS, GitHub tools
 *   - Analyst Agent (Nova Premier) — RAG + report writing
 *   - Sentinel Agent (Nova Premier) — red-team + guardrails
 *   - Supervisor Agent (Nova Premier) — orchestrates the above
 *
 * Configures collaborator relationships for the Supervisor pattern.
 */
export class AgentsStack extends cdk.Stack {
  public readonly supervisorAgentId: string;
  public readonly supervisorAgentArn: string;

  constructor(scope: Construct, id: string, props: AgentsStackProps) {
    super(scope, id, props);

    const novaPremierId = 'us.amazon.nova-premier-v1:0';
    const novaLiteId = 'us.amazon.nova-lite-v1:0';

    // ─── Shared IAM Role for Bedrock Agents ───────────────────────────
    const agentRole = new iam.Role(this, 'BedrockAgentRole', {
      roleName: 'AegisBedrockAgentRole',
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
      description: 'IAM role for Aegis-Tactical Bedrock Agents',
    });

    // Grant model invocation for both Nova models
    agentRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
      resources: [
        `arn:aws:bedrock:${this.region}::foundation-model/${novaPremierId}`,
        `arn:aws:bedrock:${this.region}::foundation-model/${novaLiteId}`,
      ],
    }));

    // Required for supervisor agent to invoke collaborator aliases.
    agentRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['bedrock:InvokeAgent', 'bedrock:GetAgentAlias'],
      resources: [`arn:aws:bedrock:${this.region}:${this.account}:agent-alias/*`],
    }));

    // Grant Knowledge Base access for the Analyst
    agentRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['bedrock:Retrieve', 'bedrock:RetrieveAndGenerate'],
      resources: [props.knowledgeBaseArn],
    }));

    // Grant Guardrail access for the Sentinel
    if (props.guardrailId) {
      agentRole.addToPolicy(new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['bedrock:ApplyGuardrail'],
        resources: [
          `arn:aws:bedrock:${this.region}:${this.account}:guardrail/${props.guardrailId}`,
        ],
      }));
    }

    // ─── Scout Agent (The Gatherer) ───────────────────────────────────
    const scoutAgent = new bedrock.CfnAgent(this, 'ScoutAgent', {
      agentName: 'aegis-scout',
      description: 'Intelligence gatherer — fetches news, RSS feeds, and GitHub activity',
      agentResourceRoleArn: agentRole.roleArn,
      foundationModel: novaLiteId,
      autoPrepare: true,
      idleSessionTtlInSeconds: 600,
      instruction: `You are the Scout agent (The Gatherer) of the Aegis-Tactical system. 
Your role is to rapidly collect intelligence from external sources. 
You have tools to fetch news headlines, parse RSS feeds, and monitor GitHub repositories. 
Always structure your findings clearly with source attribution and timestamps. 
Do NOT analyze or judge the data — only collect and report.`,
      actionGroups: [
        {
          actionGroupName: 'IntelligenceGathering',
          description: 'Tools for gathering intelligence from external sources',
          actionGroupExecutor: {
            lambda: props.functionArns.fetchNews,
          },
          apiSchema: {
            payload: JSON.stringify({
              openapi: '3.0.0',
              info: { title: 'Scout Intelligence Tools', version: '1.0.0' },
              paths: {
                '/fetch-news': {
                  post: {
                    operationId: 'fetchNews',
                    description: 'Fetch latest news from RSS feeds',
                    requestBody: {
                      content: {
                        'application/json': {
                          schema: {
                            type: 'object',
                            properties: {
                              query: { type: 'string', description: 'Search keyword filter' },
                              max_articles: { type: 'integer', description: 'Max articles to return' },
                            },
                          },
                        },
                      },
                    },
                    responses: { '200': { description: 'News articles' } },
                  },
                },
                '/fetch-rss': {
                  post: {
                    operationId: 'fetchRss',
                    description: 'Parse RSS/Atom feeds',
                    requestBody: {
                      content: {
                        'application/json': {
                          schema: {
                            type: 'object',
                            properties: {
                              feeds: { type: 'array', items: { type: 'string' } },
                              max_entries_per_feed: { type: 'integer' },
                            },
                            required: ['feeds'],
                          },
                        },
                      },
                    },
                    responses: { '200': { description: 'Feed entries' } },
                  },
                },
                '/fetch-github': {
                  post: {
                    operationId: 'fetchGithub',
                    description: 'Fetch GitHub repository activity',
                    requestBody: {
                      content: {
                        'application/json': {
                          schema: {
                            type: 'object',
                            properties: {
                              owner: { type: 'string' },
                              repo: { type: 'string' },
                              actions: { type: 'array', items: { type: 'string' } },
                              max_results: { type: 'integer' },
                            },
                            required: ['owner', 'repo'],
                          },
                        },
                      },
                    },
                    responses: { '200': { description: 'GitHub activity' } },
                  },
                },
              },
            }),
          },
        },
      ],
    });

    const scoutRuntimeAlias = new bedrock.CfnAgentAlias(this, 'ScoutRuntimeAlias', {
      agentAliasName: 'aegis-scout-runtime',
      agentId: scoutAgent.attrAgentId,
      description: 'Runtime alias used by supervisor collaboration',
    });
    scoutRuntimeAlias.addDependency(scoutAgent);

    // Grant Lambda invoke permissions to the agent role
    props.fetchNewsFunction.grantInvoke(agentRole);
    props.fetchRssFunction.grantInvoke(agentRole);
    props.fetchGithubFunction.grantInvoke(agentRole);

    // ─── Analyst Agent (The Researcher) ───────────────────────────────
    const analystAgent = new bedrock.CfnAgent(this, 'AnalystAgent', {
      agentName: 'aegis-analyst',
      description: 'Intelligence researcher — verifies data via RAG and produces reports',
      agentResourceRoleArn: agentRole.roleArn,
      foundationModel: novaPremierId,
      autoPrepare: true,
      idleSessionTtlInSeconds: 900,
      instruction: `You are the Analyst agent (The Researcher) of the Aegis-Tactical system.
Your role is to cross-reference raw intelligence against verified ground truth in the Knowledge Base.
You produce structured, evidence-based intelligence reports with confidence scores.
Always cite sources, assign precise confidence scores, and flag anything below 0.7 for human review.`,
      knowledgeBases: [
        {
          knowledgeBaseId: props.knowledgeBaseId,
          description: 'Aegis-Tactical ground truth knowledge base for intelligence verification',
          knowledgeBaseState: 'ENABLED',
        },
      ],
      actionGroups: [
        {
          actionGroupName: 'ReportWriting',
          description: 'Tools for writing analysis reports to S3',
          actionGroupExecutor: {
            lambda: props.functionArns.writeReport,
          },
          apiSchema: {
            payload: JSON.stringify({
              openapi: '3.0.0',
              info: { title: 'Analyst Report Tools', version: '1.0.0' },
              paths: {
                '/write-report': {
                  post: {
                    operationId: 'writeReport',
                    description: 'Write an intelligence report to S3',
                    requestBody: {
                      content: {
                        'application/json': {
                          schema: {
                            type: 'object',
                            properties: {
                              mission_id: { type: 'string' },
                              summary: { type: 'string' },
                              confidence_score: { type: 'number' },
                              classification: { type: 'string' },
                              findings: { type: 'array', items: { type: 'object' } },
                              recommendations: { type: 'array', items: { type: 'string' } },
                            },
                            required: ['mission_id', 'summary', 'findings'],
                          },
                        },
                      },
                    },
                    responses: { '200': { description: 'Report location' } },
                  },
                },
              },
            }),
          },
        },
      ],
    });

    const analystRuntimeAlias = new bedrock.CfnAgentAlias(this, 'AnalystRuntimeAlias', {
      agentAliasName: 'aegis-analyst-runtime',
      agentId: analystAgent.attrAgentId,
      description: 'Runtime alias used by supervisor collaboration',
    });
    analystRuntimeAlias.addDependency(analystAgent);

    props.writeReportFunction.grantInvoke(agentRole);

    // ─── Sentinel Agent (The Guard) ───────────────────────────────────
    const sentinelAgent = new bedrock.CfnAgent(this, 'SentinelAgent', {
      agentName: 'aegis-sentinel',
      description: 'Red-team guardian — checks for hallucinations, misinformation, and safety violations',
      agentResourceRoleArn: agentRole.roleArn,
      foundationModel: novaPremierId,
      autoPrepare: true,
      idleSessionTtlInSeconds: 600,
      instruction: `You are the Sentinel agent (The Guard) of the Aegis-Tactical system.
Your role is to red-team intelligence reports produced by the Analyst.
You check for hallucinations, misinformation, logical inconsistencies, and safety violations.
Always produce a verdict: PASS, CONDITIONAL_PASS, FAIL, or CRITICAL_FAIL.
You are adversarial by design — assume every claim could be wrong until proven otherwise.`,
      // Attach guardrails if configured
      ...(props.guardrailId ? {
        guardrailConfiguration: {
          guardrailIdentifier: props.guardrailId,
          guardrailVersion: props.guardrailVersion,
        },
      } : {}),
    });

    const sentinelRuntimeAlias = new bedrock.CfnAgentAlias(this, 'SentinelRuntimeAlias', {
      agentAliasName: 'aegis-sentinel-runtime',
      agentId: sentinelAgent.attrAgentId,
      description: 'Runtime alias used by supervisor collaboration',
    });
    sentinelRuntimeAlias.addDependency(sentinelAgent);

    // ─── Supervisor Agent (The General) ───────────────────────────────
    const supervisorAgent = new bedrock.CfnAgent(this, 'SupervisorAgent', {
      agentName: 'aegis-supervisor',
      description: 'Mission commander — orchestrates Scout, Analyst, and Sentinel agents',
      agentResourceRoleArn: agentRole.roleArn,
      foundationModel: novaPremierId,
      autoPrepare: true,
      idleSessionTtlInSeconds: 1800,
      instruction: `You are The General, the Supervisor of the Aegis-Tactical multi-agent intelligence system.
You NEVER perform intelligence work directly. You plan missions, delegate to your specialized agents,
and synthesize their results into final briefings.

Your team:
- Scout: Gathers intelligence from external sources (news, RSS, GitHub)
- Analyst: Verifies intelligence against the knowledge base and writes reports
- Sentinel: Red-teams reports for quality and safety (ALWAYS deploy before delivering reports)

Standard flow: Scout → Analyst → Sentinel → User Briefing.
Maximum 2 retry cycles for FAIL verdicts before escalating to the user.`,
      agentCollaboration: 'SUPERVISOR_ROUTER',
      agentCollaborators: [
        {
          collaboratorName: 'Scout',
          collaborationInstruction: 'Gather intelligence from news, RSS feeds, and GitHub repositories.',
          relayConversationHistory: 'TO_COLLABORATOR',
          agentDescriptor: {
            aliasArn: scoutRuntimeAlias.attrAgentAliasArn,
          },
        },
        {
          collaboratorName: 'Analyst',
          collaborationInstruction: 'Verify gathered intelligence and produce a structured report.',
          relayConversationHistory: 'TO_COLLABORATOR',
          agentDescriptor: {
            aliasArn: analystRuntimeAlias.attrAgentAliasArn,
          },
        },
        {
          collaboratorName: 'Sentinel',
          collaborationInstruction: 'Red-team the analyst report before final delivery.',
          relayConversationHistory: 'TO_COLLABORATOR',
          agentDescriptor: {
            aliasArn: sentinelRuntimeAlias.attrAgentAliasArn,
          },
        },
      ],
    });
    supervisorAgent.addDependency(scoutRuntimeAlias);
    supervisorAgent.addDependency(analystRuntimeAlias);
    supervisorAgent.addDependency(sentinelRuntimeAlias);

    // Ensure collaborator validation runs only after IAM policy updates complete.
    const roleDefaultPolicy = agentRole.node.tryFindChild('DefaultPolicy');
    if (roleDefaultPolicy) {
      supervisorAgent.node.addDependency(roleDefaultPolicy);
    }

    this.supervisorAgentId = supervisorAgent.attrAgentId;
    this.supervisorAgentArn = supervisorAgent.attrAgentArn;

    // ─── Outputs ──────────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'SupervisorAgentId', {
      value: supervisorAgent.attrAgentId,
      description: 'Supervisor Agent ID',
      exportName: 'AegisSupervisorAgentId',
    });

    new cdk.CfnOutput(this, 'ScoutAgentId', {
      value: scoutAgent.attrAgentId,
      description: 'Scout Agent ID',
      exportName: 'AegisScoutAgentId',
    });

    new cdk.CfnOutput(this, 'AnalystAgentId', {
      value: analystAgent.attrAgentId,
      description: 'Analyst Agent ID',
      exportName: 'AegisAnalystAgentId',
    });

    new cdk.CfnOutput(this, 'SentinelAgentId', {
      value: sentinelAgent.attrAgentId,
      description: 'Sentinel Agent ID',
      exportName: 'AegisSentinelAgentId',
    });
  }
}
