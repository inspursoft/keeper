import { AfterViewInit, Component, ComponentFactoryResolver, ElementRef, OnInit, ViewChild, ViewContainerRef } from '@angular/core';
import { GitLabCi, GitLabCiYaml, Job, NewComponnentType, Point, StagePosition } from './shared/shared.types';
import { JobComponent } from './job/job.component';
import { StageComponent } from './stage/stage.component';
import { AddNewComponent } from './add-new/add-new.component';
import { MessageService } from './shared/message.service';
import { PreviewComponent } from './preview/preview.component';
import { AppService } from './app.service';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements AfterViewInit, OnInit {
  @ViewChild('messageContainer', {read: ViewContainerRef}) messageContainer: ViewContainerRef;
  @ViewChild('canvasContainer') canvasContainer: ElementRef;
  @ViewChild('backCanvas') backCanvas: ElementRef;
  @ViewChild('componentsContainer', {read: ViewContainerRef}) componentsContainer: ViewContainerRef;
  jobComponentsMap: Map<string, Array<JobComponent>>;
  stageComponents: Array<StageComponent>;
  gitLabObject: GitLabCi;
  stageRegions: Map<string, { minX: number, maxX: number }>;
  projectList: Array<string>;
  curProjectName = '';

  constructor(private resolver: ComponentFactoryResolver,
              private appService: AppService,
              private messageService: MessageService) {
    this.jobComponentsMap = new Map<string, Array<JobComponent>>();
    this.stageComponents = new Array<StageComponent>();
    this.gitLabObject = new GitLabCi();
    this.stageRegions = new Map<string, { minX: number, maxX: number }>();
    this.projectList = Array<string>();
  }

  ngOnInit(): void {
    this.projectList = [
      'bjyd/cjbz',
      'bjyd/Cycle',
      'bjyd/demo',
      'bjyd/devops',
      'bjyd/jfgl-config',
      'bjyd/jfgl-release',
      'bjyd/jfgl',
      'bjyd/jfks-config',
      'bjyd/jfks-release',
      'bjyd/jfks',
      'bjyd/jzdz',
      'bjyd/keeper',
      'bjyd/ksxt-config',
      'bjyd/ksxt-release',
      'bjyd/ksxt',
      'bjyd/ldkb-config',
      'bjyd/ldkb-release',
      'bjyd/ldkb',
      'bjyd/ldsc-config',
      'bjyd/ldsc-release',
      'bjyd/ldsc',
      'bjyd/ldst-config',
      'bjyd/ldst-release',
      'bjyd/ldst',
      'bjyd/mbh',
      'bjyd/networkmonitor',
      'bjyd/networkMonitorFront',
      'bjyd/tyzzs',
      'bjyd/xqgl',
      'bjyd/ztst'
    ];
  }

  ngAfterViewInit(): void {
    this.messageService.registerDialogHandle(this.messageContainer, this.resolver);
    this.drawCanvasBack();
  }

  get ctx(): CanvasRenderingContext2D {
    return (this.backCanvas.nativeElement as HTMLCanvasElement).getContext('2d');
  }

  get canvasHeight(): number {
    return (this.canvasContainer.nativeElement as HTMLDivElement).offsetHeight - 2;
  }

  get canvasWidth(): number {
    return (this.canvasContainer.nativeElement as HTMLDivElement).offsetWidth - 2;
  }

  getServerYamlFile(projectName: string) {
    this.curProjectName = projectName;
    this.appService.getYamlFile(projectName).subscribe((res: GitLabCiYaml) => {
      res.alreadyParsed.subscribe(res1 => {
        this.gitLabObject = res1;
        this.beginToDraw();
      });
      res.parseFile();
    });
  }

  parseLocateYamlFile(event: Event) {
    const fileList: FileList = (event.target as HTMLInputElement).files;
    if (fileList.length > 0) {
      const file: File = fileList[0];
      if (file.name === 'gitlab-ci.yml') {
        const reader = new FileReader();
        reader.onload = (ev: ProgressEvent) => {
          const yamlStr = (ev.target as FileReader).result as string;
          const gitLabYaml = new GitLabCiYaml(yamlStr);
          gitLabYaml.alreadyParsed.subscribe((outputObject: GitLabCi) => {
            this.gitLabObject = outputObject;
            this.beginToDraw();
          });
          gitLabYaml.parseFile();
        };
        reader.readAsText(file);
      } else {
        this.messageService.showAlert('The file name is:gitlab-ci.yml', {alertType: 'warning', view: this.messageContainer});
        (event.target as HTMLInputElement).value = '';
      }
    }
  }

  send() {
    const sendStr = this.gitLabObject.getPreviewString();
    this.appService.addYamlFile(sendStr, this.curProjectName).subscribe(
      (res: string) => this.messageService.showAlert(res),
      () => {
        this.appService.updateYamlFile(sendStr, this.curProjectName).subscribe(
          (res: string) => this.messageService.showAlert(res),
          (err) => console.log(err)
        );
      }
    );
  }

  preview() {
    const factory = this.resolver.resolveComponentFactory(PreviewComponent);
    const previewComponent = this.componentsContainer.createComponent(factory);
    previewComponent.instance.gitLabObject = this.gitLabObject;
    previewComponent.instance.openModal().subscribe(() => {
      this.componentsContainer.remove(this.componentsContainer.indexOf(previewComponent.hostView));
    });
  }

  beginToDraw() {
    this.cleanEnv();
    this.drawCanvasBack();
    this.initStagesComponents();
    this.initAddNewStageComponent();
    this.initJobsComponents();
    this.initAddNewJobComponent();
    this.drawLines();
  }

  drawCanvasBack() {
    this.ctx.fillStyle = `#f9f9f9`;
    this.ctx.fillRect(0, 0, this.ctx.canvas.width, this.ctx.canvas.height);
  }

  cleanEnv() {
    (this.canvasContainer.nativeElement as HTMLDivElement).style.width =
      `${(this.gitLabObject.stages.length + 1) * 240}px`;
    this.stageComponents.splice(0, this.stageComponents.length);
    this.jobComponentsMap.clear();
    this.componentsContainer.clear();
  }

  initAddNewStageComponent() {
    const factory = this.resolver.resolveComponentFactory(AddNewComponent);
    const addNewComponent = this.componentsContainer.createComponent(factory).instance;
    addNewComponent.newType = NewComponnentType.nctStage;
    addNewComponent.left = 240 * this.gitLabObject.stages.length + 50;
    addNewComponent.top = 20;
    addNewComponent.description = 'Stage';
    addNewComponent.viewContainer = this.componentsContainer;
    addNewComponent.successNotification.subscribe((stage: string) => {
      this.gitLabObject.addNewStage(stage);
      this.beginToDraw();
    });
  }

  initAddNewJobComponent() {
    this.jobComponentsMap.forEach((jobs: Array<JobComponent>, stage: string) => {
      let left = 0;
      let top = 0;
      if (jobs.length > 0) {
        const lastJob = jobs[jobs.length - 1];
        left = lastJob.left;
        top = lastJob.top + 50;
      } else {
        const stageComponent = this.stageComponents.find(value => value.name === stage);
        left = stageComponent.left;
        top = stageComponent.top + 50;
      }
      const factory = this.resolver.resolveComponentFactory(AddNewComponent);
      const addNewComponent = this.componentsContainer.createComponent(factory).instance;
      addNewComponent.newType = NewComponnentType.nctJob;
      addNewComponent.left = left;
      addNewComponent.top = top;
      addNewComponent.description = 'Job';
      addNewComponent.viewContainer = this.componentsContainer;
      addNewComponent.job = new Job();
      addNewComponent.job.stage = stage;
      addNewComponent.successNotification.subscribe((job: Job) => {
        this.gitLabObject.addNewJob(job);
        this.beginToDraw();
      });
    });
  }

  initStagesComponents() {
    this.gitLabObject.stages.forEach((stage, stageIndex) => {
      const factory = this.resolver.resolveComponentFactory(StageComponent);
      const stageComponent = this.componentsContainer.createComponent(factory).instance;
      switch (stageIndex) {
        case 0:
          stageComponent.stagePosition = StagePosition.spFirst;
          break;
        case this.gitLabObject.stages.length - 1:
          stageComponent.stagePosition = StagePosition.spLast;
          break;
        default:
          stageComponent.stagePosition = StagePosition.spMiddle;
      }
      stageComponent.name = stage;
      stageComponent.left = 240 * stageIndex + 50;
      stageComponent.top = 20;
      stageComponent.changePosition.subscribe((isForward: boolean) => {
        this.gitLabObject.changeStagePosition(stage, isForward);
        this.beginToDraw();
      });
      stageComponent.deleteStageNotification.subscribe(() => {
        this.gitLabObject.deleteStage(stage);
        this.beginToDraw();
      });
      this.stageComponents.push(stageComponent);
      this.stageRegions.set(stage, {minX: 240 * stageIndex + 50, maxX: 240 * (stageIndex + 1)});
    });
  }

  initJobsComponents() {
    this.gitLabObject.stages.forEach((stage, stageIndex) => {
      const jobs = this.gitLabObject.getJobsByStage(stage);
      const jobComponents = new Array<JobComponent>();
      jobs.forEach((job, jobIndex) => {
        const factory = this.resolver.resolveComponentFactory(JobComponent);
        const jobRef = this.componentsContainer.createComponent(factory);
        jobRef.instance.left = 240 * stageIndex + 50;
        jobRef.instance.top = 50 + 50 * jobIndex;
        jobRef.instance.job = job;
        jobRef.instance.stage = stage;
        jobRef.instance.jobIndex = jobIndex;
        jobRef.instance.generatePoints();
        jobRef.instance.deleteJobNotification.subscribe(() => {
          this.gitLabObject.deleteJob(job);
          this.beginToDraw();
        });
        jobRef.instance.successNotification.subscribe(() => this.beginToDraw());
        jobRef.instance.moveNotification.subscribe((left: number) => this.drawRegion(stage, left));
        jobRef.instance.endMoveNotification.subscribe((position: { newLeft: number, oldLeft: number, oldTop: number }) => {
          this.stageRegions.forEach((value, key) => {
            if (value.minX < position.newLeft && position.newLeft < value.maxX && key !== stage) {
              job.stage = key;
              job.updateStageInCode(key);
              this.beginToDraw();
            } else {
              jobRef.instance.left = position.oldLeft;
              jobRef.instance.top = position.oldTop;
            }
          });
        });
        jobComponents.push(jobRef.instance);
      });
      this.jobComponentsMap.set(stage, jobComponents);
    });
  }

  drawRegion(stage: string, left: number) {
    this.stageRegions.forEach((value, key) => {
      if (value.minX < left && left < value.maxX && key !== stage) {
        this.ctx.fillStyle = `#c1c1c1`;
        this.ctx.fillRect(value.minX, 0, value.maxX - value.minX, this.ctx.canvas.height);
      } else {
        this.ctx.fillStyle = `#f9f9f9`;
        this.ctx.fillRect(value.minX, 0, value.maxX - value.minX, this.ctx.canvas.height);
      }
    });
  }

  drawLines() {
    this.ctx.beginPath();
    this.ctx.lineWidth = 1;
    this.ctx.strokeStyle = `#dfdfdf`;
    const stagesCount = this.gitLabObject.stages.length;
    let middlePoint: Point;
    let halfX: number;
    this.gitLabObject.stages.forEach((stage, stageIndex) => {
      if (stageIndex < stagesCount - 1) {
        const startJobs = this.jobComponentsMap.get(stage);
        const endJobs = this.jobComponentsMap.get(this.gitLabObject.stages[stageIndex + 1]);
        if (startJobs.length > 0 && endJobs.length > 0) {
          startJobs.forEach((jobComponent, jobIndex) => {
            if (jobIndex === 0) {
              const startPoint = startJobs[0].endPoint;
              const endPoint = endJobs[0].startPoint;
              this.ctx.moveTo(startPoint.x, startPoint.y);
              this.ctx.lineTo(endPoint.x, endPoint.y);
              this.ctx.stroke();
              halfX = Math.abs(startPoint.x - endPoint.x) / 2;
              middlePoint = Point.getMiddlePoint(endPoint, startPoint);
            } else {
              const startPoint = jobComponent.endPoint;
              this.ctx.moveTo(startPoint.x, startPoint.y);
              this.ctx.bezierCurveTo(startPoint.x + halfX, startPoint.y, middlePoint.x - halfX,
                middlePoint.y, middlePoint.x, middlePoint.y);
              this.ctx.stroke();
            }
          });
          endJobs.forEach((jobComponent, jobIndex) => {
            if (jobIndex > 0) {
              const startPoint = jobComponent.startPoint;
              this.ctx.moveTo(startPoint.x, startPoint.y);
              this.ctx.bezierCurveTo(startPoint.x - halfX, startPoint.y, middlePoint.x + halfX,
                middlePoint.y, middlePoint.x, middlePoint.y);
              this.ctx.stroke();
            }
          });
        }
      }
    });
  }
}
