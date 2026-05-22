import * as cdk from 'aws-cdk-lib';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as cw_actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { Construct } from 'constructs';

export interface ObservabilityStackProps extends cdk.StackProps {
  /** Step Functions state machine to monitor */
  stateMachine: sfn.IStateMachine;
  /** Lambda functions to monitor */
  fetchNewsFunction: lambda.IFunction;
  fetchRssFunction: lambda.IFunction;
  fetchGithubFunction: lambda.IFunction;
  writeReportFunction: lambda.IFunction;
}

/**
 * ObservabilityStack — Phase 4
 *
 * Full observability suite for Aegis-Tactical:
 *   - CloudWatch Log Groups for structured logging
 *   - CloudWatch Dashboard with key operational metrics
 *   - Alarms on agent failures, Lambda errors, and latency
 *   - SNS topic for alert notifications
 */
export class ObservabilityStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ObservabilityStackProps) {
    super(scope, id, props);

    // ─── SNS Alert Topic ──────────────────────────────────────────────
    const alertTopic = new sns.Topic(this, 'AlertTopic', {
      topicName: 'aegis-tactical-alerts',
      displayName: 'Aegis-Tactical System Alerts',
    });

    // ─── Log Groups ───────────────────────────────────────────────────
    new logs.LogGroup(this, 'SupervisorLogs', {
      logGroupName: '/aegis-tactical/agents/supervisor',
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    new logs.LogGroup(this, 'ScoutLogs', {
      logGroupName: '/aegis-tactical/agents/scout',
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    new logs.LogGroup(this, 'AnalystLogs', {
      logGroupName: '/aegis-tactical/agents/analyst',
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    new logs.LogGroup(this, 'SentinelLogs', {
      logGroupName: '/aegis-tactical/agents/sentinel',
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ─── CloudWatch Dashboard ─────────────────────────────────────────
    const dashboard = new cloudwatch.Dashboard(this, 'AegisDashboard', {
      dashboardName: 'AegisTactical-Operations',
      defaultInterval: cdk.Duration.hours(6),
    });

    // ── Mission Execution Metrics ─────────────────────────────────────
    const missionSuccesses = props.stateMachine.metricSucceeded({
      period: cdk.Duration.minutes(5),
      statistic: 'Sum',
      label: 'Successful Missions',
    });

    const missionFailures = props.stateMachine.metricFailed({
      period: cdk.Duration.minutes(5),
      statistic: 'Sum',
      label: 'Failed Missions',
    });

    const missionDuration = props.stateMachine.metricTime({
      period: cdk.Duration.minutes(5),
      statistic: 'Average',
      label: 'Avg Mission Duration',
    });

    const missionStarted = props.stateMachine.metricStarted({
      period: cdk.Duration.minutes(5),
      statistic: 'Sum',
      label: 'Missions Started',
    });

    dashboard.addWidgets(
      new cloudwatch.TextWidget({
        markdown: '# 🛡️ Aegis-Tactical Operations Dashboard\n---',
        width: 24,
        height: 1,
      }),
    );

    dashboard.addWidgets(
      new cloudwatch.SingleValueWidget({
        title: 'Mission Overview (Last 6 Hours)',
        metrics: [missionStarted, missionSuccesses, missionFailures],
        width: 12,
        height: 4,
      }),
      new cloudwatch.GraphWidget({
        title: 'Mission Duration',
        left: [missionDuration],
        width: 12,
        height: 4,
      }),
    );

    // ── Lambda Tool Metrics ───────────────────────────────────────────
    const lambdaFunctions = [
      { fn: props.fetchNewsFunction, name: 'fetch_news' },
      { fn: props.fetchRssFunction, name: 'fetch_rss' },
      { fn: props.fetchGithubFunction, name: 'fetch_github' },
      { fn: props.writeReportFunction, name: 'write_report' },
    ];

    const invocationMetrics: cloudwatch.IMetric[] = [];
    const errorMetrics: cloudwatch.IMetric[] = [];
    const durationMetrics: cloudwatch.IMetric[] = [];

    for (const { fn, name } of lambdaFunctions) {
      invocationMetrics.push(fn.metricInvocations({
        period: cdk.Duration.minutes(5),
        statistic: 'Sum',
        label: name,
      }));
      errorMetrics.push(fn.metricErrors({
        period: cdk.Duration.minutes(5),
        statistic: 'Sum',
        label: name,
      }));
      durationMetrics.push(fn.metricDuration({
        period: cdk.Duration.minutes(5),
        statistic: 'Average',
        label: name,
      }));
    }

    dashboard.addWidgets(
      new cloudwatch.TextWidget({
        markdown: '## ⚡ Lambda Tool Performance\n---',
        width: 24,
        height: 1,
      }),
    );

    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Tool Invocations',
        left: invocationMetrics,
        width: 8,
        height: 6,
      }),
      new cloudwatch.GraphWidget({
        title: 'Tool Errors',
        left: errorMetrics,
        width: 8,
        height: 6,
      }),
      new cloudwatch.GraphWidget({
        title: 'Tool Latency (ms)',
        left: durationMetrics,
        width: 8,
        height: 6,
      }),
    );

    // ─── Alarms ───────────────────────────────────────────────────────

    // Mission failure alarm
    const missionFailureAlarm = new cloudwatch.Alarm(this, 'MissionFailureAlarm', {
      alarmName: 'aegis-mission-failure',
      alarmDescription: 'More than 3 mission failures in 15 minutes',
      metric: props.stateMachine.metricFailed({
        period: cdk.Duration.minutes(15),
        statistic: 'Sum',
      }),
      threshold: 3,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    missionFailureAlarm.addAlarmAction(new cw_actions.SnsAction(alertTopic));

    // Lambda error rate alarm (per function)
    for (const { fn, name } of lambdaFunctions) {
      const alarm = new cloudwatch.Alarm(this, `${name}ErrorAlarm`, {
        alarmName: `aegis-${name}-errors`,
        alarmDescription: `Lambda ${name} error rate exceeds threshold`,
        metric: fn.metricErrors({
          period: cdk.Duration.minutes(5),
          statistic: 'Sum',
        }),
        threshold: 5,
        evaluationPeriods: 2,
        comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      alarm.addAlarmAction(new cw_actions.SnsAction(alertTopic));
    }

    // Mission timeout alarm
    const timeoutAlarm = new cloudwatch.Alarm(this, 'MissionTimeoutAlarm', {
      alarmName: 'aegis-mission-timeout',
      alarmDescription: 'Mission execution time exceeds 30 minutes',
      metric: props.stateMachine.metricTime({
        period: cdk.Duration.minutes(5),
        statistic: 'Maximum',
      }),
      threshold: 1800000, // 30 minutes in milliseconds
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    timeoutAlarm.addAlarmAction(new cw_actions.SnsAction(alertTopic));

    // ─── Outputs ──────────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'DashboardUrl', {
      value: `https://${this.region}.console.aws.amazon.com/cloudwatch/home?region=${this.region}#dashboards:name=AegisTactical-Operations`,
      description: 'CloudWatch Dashboard URL',
      exportName: 'AegisDashboardUrl',
    });

    new cdk.CfnOutput(this, 'AlertTopicArn', {
      value: alertTopic.topicArn,
      description: 'SNS Alert Topic ARN — subscribe for notifications',
      exportName: 'AegisAlertTopicArn',
    });
  }
}
