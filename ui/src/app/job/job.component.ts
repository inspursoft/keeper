import { Component, ComponentFactoryResolver, HostBinding, HostListener, OnDestroy, OnInit, ViewContainerRef } from '@angular/core';
import { BUTTON_STYLE, Job, Message, Point, RETURN_STATUS } from '../shared/shared.types';
import { JobEditorComponent } from '../job-editor/job-editor.component';
import { Subject } from 'rxjs';
import { MessageService } from '../shared/message.service';

@Component({
  selector: 'app-job',
  templateUrl: './job.component.html',
  styleUrls: ['./job.component.css']
})
export class JobComponent implements OnInit, OnDestroy {
  @HostBinding('style.position') position = 'absolute';
  @HostBinding('style.left.px') left = 0;
  @HostBinding('style.top.px') top = 0;
  @HostBinding('style.z-index') zindex = 0;
  successNotification: Subject<Job>;
  deleteJobNotification: Subject<Job>;
  moveNotification: Subject<number>;
  endMoveNotification: Subject<{newLeft: number, oldLeft: number, oldTop: number}>;
  startPoint: Point;
  endPoint: Point;
  job: Job;
  stage = '';
  jobIndex = 0;
  isShowIcons = false;
  isInMoveStatus = false;
  oldPosition: { left: number, top: number, clientX: number, clientY: number };

  @HostListener('mouseenter', ['$event']) showArrows(event) {
    this.isShowIcons = true;
  }

  @HostListener('mouseleave', ['$event']) hideArrows(event) {
    this.isShowIcons = false;
  }

  @HostListener('mousedown', ['$event']) setMoveStatus(event: MouseEvent) {
    this.isInMoveStatus = true;
    this.zindex = 10;
    this.oldPosition = {left: this.left, top: this.top, clientX: event.clientX, clientY: event.clientY};
  }

  @HostListener('mouseup', ['$event']) clearMoveStatus(event) {
    this.isInMoveStatus = false;
    this.zindex = 0;
    this.endMoveNotification.next({newLeft: this.left, oldLeft: this.oldPosition.left, oldTop: this.oldPosition.top});
  }

  @HostListener('mousemove', ['$event']) setNewPosition(event: MouseEvent) {
    if (this.isInMoveStatus) {
      this.left = this.oldPosition.left + event.clientX - this.oldPosition.clientX;
      this.top = this.oldPosition.top + event.clientY - this.oldPosition.clientY;
      this.moveNotification.next(this.left);
    }
  }

  constructor(private resolver: ComponentFactoryResolver,
              private viewContainer: ViewContainerRef,
              private messageService: MessageService) {
    this.successNotification = new Subject();
    this.deleteJobNotification = new Subject();
    this.moveNotification = new Subject();
    this.endMoveNotification = new Subject();
  }

  ngOnInit() {

  }

  ngOnDestroy(): void {
    delete this.successNotification;
    delete this.deleteJobNotification;
    delete this.moveNotification;
    delete this.endMoveNotification;
  }

  editJob() {
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

  generatePoints() {
    this.startPoint = Point.newPointByValue(this.left, this.top + 20);
    this.endPoint = Point.newPointByValue(this.left + 186, this.top + 20);
  }

  emitDeleteJob() {
    this.messageService.showDialog('Are you sure to delete the Job?',
      {title: 'Confirm', view: this.viewContainer, buttonStyle: BUTTON_STYLE.DELETION})
      .subscribe((meg: Message) => {
          if (meg.returnStatus === RETURN_STATUS.rsConfirm) {
            this.deleteJobNotification.next(this.job);
          }
        }
      );
  }
}
