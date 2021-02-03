import { Component, HostBinding, HostListener, OnInit, ViewContainerRef } from '@angular/core';
import { BUTTON_STYLE, Message, RETURN_STATUS, StagePosition } from '../shared/shared.types';
import { Subject } from 'rxjs';
import { MessageService } from '../shared/message.service';

@Component({
  selector: 'app-stage',
  templateUrl: './stage.component.html',
  styleUrls: ['./stage.component.css']
})
export class StageComponent implements OnInit {
  @HostBinding('style.position') position = 'absolute';
  @HostBinding('style.left.px') left = 0;
  @HostBinding('style.top.px') top = 0;
  changePosition: Subject<boolean>;
  deleteStageNotification: Subject<string>;
  stagePosition: StagePosition = StagePosition.spFirst;
  name = '';
  isShowIcons = false;

  @HostListener('mouseenter', ['$event'])
  showArrows(event) {
    this.isShowIcons = true;
  }

  @HostListener('mouseleave', ['$event'])
  hideArrows(event) {
    this.isShowIcons = false;
  }

  constructor(private messageService: MessageService,
              private viewContainer: ViewContainerRef) {
    this.changePosition = new Subject<boolean>();
    this.deleteStageNotification = new Subject<string>();
  }

  ngOnInit() {
  }

  emitChangePosition(isForward: boolean) {
    this.changePosition.next(isForward);
  }

  emitDeleteStage() {
    this.messageService.showDialog('Are you sure to delete the Stage?',
      {title: 'Confirm', view: this.viewContainer, buttonStyle: BUTTON_STYLE.DELETION})
      .subscribe((meg: Message) => {
          if (meg.returnStatus === RETURN_STATUS.rsConfirm) {
            this.deleteStageNotification.next(this.name);
          }
        }
      );
  }

  getArrowsColor(isForward: boolean): string {
    return ((this.isShowIcons && this.stagePosition === StagePosition.spFirst && !isForward) ||
      (this.isShowIcons && this.stagePosition === StagePosition.spLast && isForward) ||
      (this.isShowIcons && this.stagePosition === StagePosition.spMiddle)) ? '#40b214' : 'transparent';
  }

}
