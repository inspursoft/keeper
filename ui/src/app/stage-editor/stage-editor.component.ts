import { Component, OnDestroy, OnInit } from '@angular/core';
import { ModalChildBase } from '../shared/class-base/modal-child-base';
import { MessageService } from '../shared/message.service';
import { Subject } from 'rxjs';

@Component({
  selector: 'app-stage-editor',
  templateUrl: './stage-editor.component.html',
  styleUrls: ['./stage-editor.component.css']
})
export class StageEditorComponent extends ModalChildBase implements OnInit, OnDestroy {
  name = '';
  successNotification: Subject<string>;

  constructor(protected messageService: MessageService) {
    super();
    this.successNotification = new Subject();
  }

  ngOnInit() {
  }

  ngOnDestroy() {
    delete this.successNotification;
  }

  cancel() {
    this.modalOpened = false;
  }

  save() {
    if (this.verifyInputExValid()) {
      this.successNotification.next(this.name);
      this.modalOpened = false;
    }
  }

}
