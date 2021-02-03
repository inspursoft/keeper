import YAML from 'yaml';
import { Subject, TimeoutError } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';
import { Type } from '@angular/core';

export enum RelativePosition {
  wrpSame, wrpLeft, wrpRight, wrpBottom, wrpTop, wrpQuadrantA, wrpQuadrantB, wrpQuadrantC, wrpQuadrantD
}

export enum StagePosition {
  spFirst, spMiddle, spLast
}

export enum RETURN_STATUS {
  rsNone, rsConfirm, rsCancel
}

export enum BUTTON_STYLE {
  CONFIRMATION = 1, DELETION, YES_NO, ONLY_CONFIRM
}

export enum GlobalAlertType {
  gatNormal, gatShowDetail
}

export enum NewComponnentType {
  nctJob, nctStage
}

export type AlertType = 'success' | 'danger' | 'info' | 'warning';

export class AlertMessage {
  message = '';
  alertType: AlertType = 'success';
}

export class GlobalAlertMessage {
  type: GlobalAlertType = GlobalAlertType.gatNormal;
  message = '';
  alertType: AlertType = 'danger';
  errorObject: HttpErrorResponse | Type<Error> | TimeoutError;
  endMessage = '';
}

export class Message {
  title = '';
  message = '';
  data: any;
  buttonStyle: BUTTON_STYLE = BUTTON_STYLE.CONFIRMATION;
  returnStatus: RETURN_STATUS = RETURN_STATUS.rsNone;
}

export class GitLabCi {
  stages: Array<string>;
  jobs: Array<Job>;
  beforeScript: Array<string>;

  constructor() {
    this.stages = new Array<string>();
    this.jobs = new Array<Job>();
    this.beforeScript = new Array<string>();
  }

  getPreviewString(): string {
    const preview = {};
    if (this.beforeScript.length > 0) {
      Reflect.set(preview, 'before_script', this.beforeScript);
    }
    if (this.stages.length > 0) {
      Reflect.set(preview, 'stages', this.stages);
    }
    if (this.jobs.length > 0) {
      this.jobs.forEach(job => {
        const out = YAML.parse(job.code);
        Reflect.set(preview, job.name, out);
      });
    }
    return YAML.stringify(preview);
  }

  getJobsByStage(stage: string): Array<Job> {
    return this.jobs.filter(value => value.stage === stage);
  }

  changeStagePosition(stage: string, isForward: boolean) {
    const oldIndex = this.stages.indexOf(stage);
    if (isForward) {
      this.stages[oldIndex] = this.stages[oldIndex + 1];
      this.stages[oldIndex + 1] = stage;
    } else {
      this.stages[oldIndex] = this.stages[oldIndex - 1];
      this.stages[oldIndex - 1] = stage;
    }
  }

  deleteStage(stage: string) {
    this.jobs = this.jobs.filter(job => job.stage !== stage);
    this.stages.splice(this.stages.indexOf(stage), 1);
  }

  deleteJob(job: Job) {
    this.jobs.splice(this.jobs.indexOf(job), 1);
  }

  addNewJob(job: Job) {
    this.jobs.push(job);
  }

  addNewStage(stage: string) {
    this.stages.push(stage);
  }
}

export class GitLabCiYaml {
  private yamlObject: object;
  public outputObject: GitLabCi;
  public alreadyParsed: Subject<GitLabCi>;

  constructor(public originStr: string) {
    this.alreadyParsed = new Subject<GitLabCi>();
    this.outputObject = new GitLabCi();
  }

  parseFile() {
    if (this.originStr) {
      this.yamlObject = YAML.parse(this.originStr);
      // init before_script
      if (Reflect.has(this.yamlObject, 'before_script')) {
        const beforeScript = Reflect.get(this.yamlObject, 'before_script') as Array<string>;
        beforeScript.forEach(value => this.outputObject.beforeScript.push(value));
      }
      // init stages
      if (Reflect.has(this.yamlObject, 'stages')) {
        const stages = Reflect.get(this.yamlObject, 'stages') as Array<string>;
        stages.forEach(value => this.outputObject.stages.push(value));
      }
      // init jobs
      Reflect.ownKeys(this.yamlObject).forEach(key => {
        const prop = Reflect.get(this.yamlObject, key);
        if (prop && Reflect.has(prop, 'stage')) {
          const job = new Job();
          job.code = YAML.stringify(prop);
          job.name = key.toString();
          if (Reflect.has(prop, 'stage')) {
            job.stage = Reflect.get(prop, 'stage');
          }
          this.outputObject.jobs.push(job);
        }
      });
      this.alreadyParsed.next(this.outputObject);
    }
  }
}

export class Job {
  stage = '';
  name = '';
  code = '';

  constructor() {
  }

  updateStage() {
    const codeObject = YAML.parse(this.code);
    if (codeObject && Reflect.has(codeObject, 'stage')) {
      this.stage = Reflect.get(codeObject, 'stage');
    }
  }

  updateStageInCode(stage: string) {
    const codeObject = YAML.parse(this.code);
    if (codeObject && Reflect.has(codeObject, 'stage')) {
      Reflect.set(codeObject, 'stage', stage);
      this.code = YAML.stringify(codeObject);
    }
  }
}

export class Point {
  x = 0;
  y = 0;

  static newPoint(): Point {
    return new Point();
  }

  static newPointByPoint(point: Point): Point {
    const result = new Point();
    result.x = point.x;
    result.y = point.y;
    return result;
  }

  static newPointByValue(x, y: number): Point {
    const result = new Point();
    result.x = x;
    result.y = y;
    return result;
  }

  static getMiddlePoint(point1: Point, point2: Point) {
    const x = (point1.x + point2.x) / 2;
    const y = (point1.y + point2.y) / 2;
    return Point.newPointByValue(x, y);
  }

  isSamePoint(point: Point): boolean {
    return Math.abs(this.x - point.x) < 0.01 && Math.abs(this.y - point.y) < 0.01;
  }

  isSameX(point: Point): boolean {
    return this.x + 0.01 > point.x && this.x < point.x + 0.01;
  }

  isSameY(point: Point): boolean {
    return this.y + 0.01 > point.y && this.y < point.y + 0.01;
  }

  distance(point: Point): number {
    const distancePowX = Math.pow(Math.abs(this.x - point.x), 2);
    const distancePowY = Math.pow(Math.abs(this.y - point.y), 2);
    return Math.sqrt(distancePowX + distancePowY);
  }

  calculateRelativePosition(point: Point): RelativePosition {
    if (this.isSamePoint(point)) {
      return RelativePosition.wrpSame;
    } else if (this.isSameX(point)) {
      if (point.y > this.y) {
        return RelativePosition.wrpBottom;
      } else {
        return RelativePosition.wrpTop;
      }
    } else if (this.isSameY(point)) {
      if (point.x > this.x) {
        return RelativePosition.wrpRight;
      } else {
        return RelativePosition.wrpLeft;
      }
    } else if (point.x > this.x && point.y < this.y) {
      return RelativePosition.wrpQuadrantA;
    } else if (point.x < this.x && point.y > this.y) {
      return RelativePosition.wrpQuadrantB;
    } else if (point.x < this.x && point.y > this.y) {
      return RelativePosition.wrpQuadrantC;
    } else if (point.x > this.x && point.y > this.y) {
      return RelativePosition.wrpQuadrantD;
    }
  }
}

