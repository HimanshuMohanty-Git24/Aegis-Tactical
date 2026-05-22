import * as cdk from 'aws-cdk-lib';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

export interface WorkflowStackProps extends cdk.StackProps {
  /** Supervisor Agent ID */
  supervisorAgentId: string;
  /** Supervisor Agent ARN */
  supervisorAgentArn: string;
  /** Lambda functions for direct tool invocation */
  fetchNewsFunction: lambda.IFunction;
  fetchRssFunction: lambda.IFunction;
  fetchGithubFunction: lambda.IFunction;
  writeReportFunction: lambda.IFunction;
}

/**
 * WorkflowStack — Phase 4
 *
 * Provisions the Step Functions state machine for long-running "Missions":
 *   - Invoke Scout (gather intelligence)
 *   - Invoke Analyst (verify + report)
 *   - Invoke Sentinel (red-team)
 *   - Conditional retry loop on FAIL verdicts
 *   - Error handling with exponential backoff
 *   - Optional EventBridge schedule for 24-hour watch cycles
 */
export class WorkflowStack extends cdk.Stack {
  public readonly stateMachine: sfn.StateMachine;

  constructor(scope: Construct, id: string, props: WorkflowStackProps) {
    super(scope, id, props);

    // ─── Step 1: Initialize Mission ───────────────────────────────────
    const initMission = new sfn.Pass(this, 'InitializeMission', {
      comment: 'Initialize mission state with metadata',
      parameters: {
        'missionId.$': "States.Format('mission-{}', $$.Execution.Name)",
        'objective.$': '$.objective',
        'retryCount': 0,
        'maxRetries': 2,
        'status': 'INITIATED',
        'startedAt.$': '$$.Execution.StartTime',
      },
    });

    // ─── Step 2: Invoke Scout (Gather Intelligence) ───────────────────
    const invokeScout = new tasks.LambdaInvoke(this, 'InvokeScout', {
      comment: 'Deploy Scout to gather intelligence from external sources',
      lambdaFunction: props.fetchNewsFunction,
      payload: sfn.TaskInput.fromObject({
        'query.$': '$.objective',
        'max_articles': 15,
      }),
      resultPath: '$.scoutResults',
      resultSelector: {
        'payload.$': '$.Payload',
      },
      retryOnServiceExceptions: true,
    });

    invokeScout.addRetry({
      errors: ['Lambda.ServiceException', 'Lambda.AWSLambdaException'],
      interval: cdk.Duration.seconds(2),
      maxAttempts: 3,
      backoffRate: 2,
    });

    invokeScout.addCatch(new sfn.Pass(this, 'ScoutFailed', {
      comment: 'Scout failed — continue with partial data',
      parameters: {
        'missionId.$': '$.missionId',
        'objective.$': '$.objective',
        'retryCount.$': '$.retryCount',
        'maxRetries.$': '$.maxRetries',
        'status': 'SCOUT_FAILED',
        'scoutResults': { payload: { status: 'error', articles: [] } },
      },
    }), { resultPath: '$' });

    // ─── Step 3: Invoke Analyst (Analyze + Verify) ────────────────────
    const invokeAnalyst = new tasks.LambdaInvoke(this, 'InvokeAnalyst', {
      comment: 'Deploy Analyst to verify intelligence against Knowledge Base',
      lambdaFunction: props.writeReportFunction,
      payload: sfn.TaskInput.fromObject({
        'mission_id.$': '$.missionId',
        'agent': 'Analyst',
        'classification': 'UNCLASSIFIED',
        'objective.$': '$.objective',
        'scout_payload.$': '$.scoutResults.payload',
        'summary.$': "States.Format('Analysis of intelligence gathered for objective: {}', $.objective)",
        'findings': [{
          'title': 'Intelligence Gathered',
          'severity': 'MEDIUM',
          'source': 'Scout Agent',
          'verified': false,
          'description.$': "States.JsonToString($.scoutResults.payload)",
        }],
        'recommendations': ['Further verification recommended'],
      }),
      resultPath: '$.analystResults',
      resultSelector: {
        'payload.$': '$.Payload',
      },
    });

    invokeAnalyst.addRetry({
      errors: ['Lambda.ServiceException'],
      interval: cdk.Duration.seconds(5),
      maxAttempts: 2,
      backoffRate: 2,
    });

    // ─── Step 4: Invoke Sentinel (Red-Team) ───────────────────────────
    const invokeSentinel = new tasks.LambdaInvoke(this, 'InvokeSentinel', {
      comment: 'Deploy Sentinel to red-team the analysis report',
      lambdaFunction: props.writeReportFunction,
      payload: sfn.TaskInput.fromObject({
        'mission_id.$': "States.Format('{}-sentinel', $.missionId)",
        'agent': 'Sentinel',
        'classification': 'INTERNAL',
        'objective.$': '$.objective',
        'confidence_score.$': '$.analystResults.payload.confidence_score',
        'summary.$': "States.Format('Sentinel red-team assessment for analyst verdict {}', $.analystResults.payload.analyst_verdict)",
        'findings': [{
          'title': 'Red-Team Review',
          'severity': 'LOW',
          'source': 'Sentinel Agent',
          'verified': true,
          'description.$': "States.Format('Analyst direct answer: {}', $.analystResults.payload.direct_answer)",
        }],
        'red_team_assessment': {
          'verdict.$': '$.analystResults.payload.suggested_sentinel_verdict',
          'hallucination_risk.$': '$.analystResults.payload.hallucination_risk',
          'misinformation_flags.$': '$.analystResults.payload.misinformation_flags',
          'notes.$': "States.Format('Analyst verdict: {}. Confidence: {}', $.analystResults.payload.analyst_verdict, $.analystResults.payload.confidence_score)",
        },
        'recommendations.$': '$.analystResults.payload.recommendations',
      }),
      resultPath: '$.sentinelResults',
      resultSelector: {
        'verdict.$': '$.Payload.suggested_sentinel_verdict',
        'payload.$': '$.Payload',
      },
    });

    // ─── Step 5: Evaluate Sentinel Verdict ────────────────────────────
    const checkVerdict = new sfn.Choice(this, 'EvaluateVerdict', {
      comment: 'Check if the Sentinel approved the report',
    });

    // ─── PASS: Publish Final Report ───────────────────────────────────
    const publishReportPass = new sfn.Pass(this, 'PublishReportPass', {
      comment: 'Mission completed — report approved by Sentinel (PASS)',
      parameters: {
        'missionId.$': '$.missionId',
        'objective.$': '$.objective',
        'status': 'COMPLETED',
        'verdict': 'PASS',
        'reportLocation.$': '$.analystResults.payload.report_location',
        'directAnswer.$': '$.analystResults.payload.direct_answer',
        'analystVerdict.$': '$.analystResults.payload.analyst_verdict',
        'confidenceScore.$': '$.analystResults.payload.confidence_score',
      },
    });

    const publishReportConditional = new sfn.Pass(this, 'PublishReportConditional', {
      comment: 'Mission completed — report approved with conditions (CONDITIONAL_PASS)',
      parameters: {
        'missionId.$': '$.missionId',
        'objective.$': '$.objective',
        'status': 'COMPLETED_WITH_CAVEATS',
        'verdict': 'CONDITIONAL_PASS',
        'reportLocation.$': '$.analystResults.payload.report_location',
        'directAnswer.$': '$.analystResults.payload.direct_answer',
        'analystVerdict.$': '$.analystResults.payload.analyst_verdict',
        'confidenceScore.$': '$.analystResults.payload.confidence_score',
      },
    });

    // ─── FAIL: Check Retry Count ──────────────────────────────────────
    const incrementRetry = new sfn.Pass(this, 'IncrementRetryCount', {
      comment: 'Increment retry counter for re-analysis',
      parameters: {
        'missionId.$': '$.missionId',
        'objective.$': '$.objective',
        'retryCount.$': 'States.MathAdd($.retryCount, 1)',
        'maxRetries.$': '$.maxRetries',
        'status': 'RETRYING',
        'scoutResults.$': '$.scoutResults',
      },
    });

    const checkRetries = new sfn.Choice(this, 'CheckRetryLimit', {
      comment: 'Check if we have exceeded the retry limit',
    });

    // ─── CRITICAL FAIL: Escalate ──────────────────────────────────────
    const escalateCritical = new sfn.Pass(this, 'EscalateCriticalFail', {
      comment: 'Critical failure — escalating to user immediately',
      parameters: {
        'missionId.$': '$.missionId',
        'objective.$': '$.objective',
        'status': 'ESCALATED',
        'reason': 'Sentinel flagged CRITICAL_FAIL. Immediate human review required.',
        'retryCount.$': '$.retryCount',
      },
    });

    const escalateRetryExhausted = new sfn.Pass(this, 'EscalateRetryExhausted', {
      comment: 'Retry limit exceeded — escalating to user for manual review',
      parameters: {
        'missionId.$': '$.missionId',
        'objective.$': '$.objective',
        'status': 'ESCALATED',
        'reason': 'Sentinel repeatedly rejected the report. Manual review required.',
        'retryCount.$': '$.retryCount',
      },
    });

    // ─── Terminal States ──────────────────────────────────────────────
    const missionCompletePass = new sfn.Succeed(this, 'MissionCompletePass', {
      comment: 'Mission finished — report delivered (PASS)',
    });

    const missionCompleteConditional = new sfn.Succeed(this, 'MissionCompleteConditional', {
      comment: 'Mission finished — report delivered with caveats',
    });

    const missionEscalatedCritical = new sfn.Succeed(this, 'MissionEscalatedCritical', {
      comment: 'Mission escalated — critical failure',
    });

    const missionEscalatedRetry = new sfn.Succeed(this, 'MissionEscalatedRetry', {
      comment: 'Mission escalated — retry limit exceeded',
    });

    // ─── Wire the State Machine ───────────────────────────────────────
    const definition = initMission
      .next(invokeScout)
      .next(invokeAnalyst)
      .next(invokeSentinel)
      .next(
        checkVerdict
          .when(
            sfn.Condition.stringEquals('$.sentinelResults.verdict', 'PASS'),
            publishReportPass.next(missionCompletePass)
          )
          .when(
            sfn.Condition.stringEquals('$.sentinelResults.verdict', 'CONDITIONAL_PASS'),
            publishReportConditional.next(missionCompleteConditional)
          )
          .when(
            sfn.Condition.stringEquals('$.sentinelResults.verdict', 'CRITICAL_FAIL'),
            escalateCritical.next(missionEscalatedCritical)
          )
          .otherwise(
            incrementRetry.next(
              checkRetries
                .when(
                  sfn.Condition.numberGreaterThanEqualsJsonPath('$.retryCount', '$.maxRetries'),
                  escalateRetryExhausted.next(missionEscalatedRetry)
                )
                .otherwise(invokeAnalyst)
            )
          )
      );

    // ─── Log Group for State Machine ──────────────────────────────────
    const logGroup = new logs.LogGroup(this, 'MissionStateMachineLogs', {
      logGroupName: '/aegis-tactical/step-functions/missions',
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ─── Create the State Machine ─────────────────────────────────────
    this.stateMachine = new sfn.StateMachine(this, 'MissionStateMachine', {
      stateMachineName: 'aegis-mission-executor',
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      timeout: cdk.Duration.hours(2),
      tracingEnabled: true,
      logs: {
        destination: logGroup,
        level: sfn.LogLevel.ALL,
        includeExecutionData: true,
      },
    });

    // ─── EventBridge Schedule (24-hour Watch Cycle) ───────────────────
    const watchScheduleRule = new events.Rule(this, 'DailyWatchCycle', {
      ruleName: 'aegis-daily-watch',
      description: 'Triggers a daily intelligence sweep mission every 24 hours',
      schedule: events.Schedule.rate(cdk.Duration.hours(24)),
      enabled: false, // Disabled by default — enable in production
    });

    watchScheduleRule.addTarget(
      new targets.SfnStateMachine(this.stateMachine, {
        input: events.RuleTargetInput.fromObject({
          objective: 'Conduct daily intelligence sweep: gather latest news, check monitored repositories, and verify against ground truth.',
        }),
      })
    );

    // ─── Outputs ──────────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'StateMachineArn', {
      value: this.stateMachine.stateMachineArn,
      description: 'Step Functions State Machine ARN',
      exportName: 'AegisMissionStateMachineArn',
    });

    new cdk.CfnOutput(this, 'StateMachineName', {
      value: this.stateMachine.stateMachineName!,
      description: 'Step Functions State Machine name',
      exportName: 'AegisMissionStateMachineName',
    });
  }
}
