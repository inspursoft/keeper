import { Component, ComponentFactoryResolver, HostBinding, OnDestroy, OnInit, ViewContainerRef } from '@angular/core';
import { Subject } from 'rxjs';
import { JobEditorComponent } from '../job-editor/job-editor.component';
import { Job, NewComponnentType } from '../shared/shared.types';
import { StageEditorComponent } from '../stage-editor/stage-editor.component';

@Component({
  selector: 'app-add-new',
  templateUrl: './add-new.component.html',
  styleUrls: ['./add-new.component.css']
})
export class AddNewComponent implements OnInit, OnDestroy {
  @HostBinding('style.position') position = 'absolute';
  @HostBinding('style.left.px') left = 0;
  @HostBinding('style.top.px') top = 0;
  newType: NewComponnentType = NewComponnentType.nctJob;
  successNotification: Subject<any>;
  description = '';
  job: Job;
  stage: string;
  viewContainer: ViewContainerRef;

  constructor(private resolver: ComponentFactoryResolver) {
    this.successNotification = new Subject();
  }


  ngOnInit() {

  }

  ngOnDestroy(): void {
    delete this.successNotification;
  }

  addNewJob() {
    const jobFactory = this.resolver.resolveComponentFactory(JobEditorComponent);
    const jobEditorRef = this.viewContainer.createComponent(jobFactory);
    jobEditorRef.instance.job = this.job;
    jobEditorRef.instance.openModal().subscribe(() => {
      this.viewContainer.remove(this.viewContainer.indexOf(jobEditorRef.hostView));
    });
    jobEditorRef.instance.successNotification.subscribe((job: Job) => {
      this.successNotification.next(job);
    });
  }

  addNewStage() {
    const stageFactory = this.resolver.resolveComponentFactory(StageEditorComponent);
    const stageEditorRef = this.viewContainer.createComponent(stageFactory);
    stageEditorRef.instance.name = this.stage;
    stageEditorRef.instance.openModal().subscribe(() => {
      this.viewContainer.remove(this.viewContainer.indexOf(stageEditorRef.hostView));
    });
    stageEditorRef.instance.successNotification.subscribe((stage: string) => {
      this.successNotification.next(stage);
    });
  }

  addNewClick(event: Event) {
    this.newType === NewComponnentType.nctJob ? this.addNewJob() : this.addNewStage();
  }

}
